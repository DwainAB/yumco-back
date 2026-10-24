/**
 * Assistant IA du restaurateur (ai_service.py) : appel à l'API Responses d'OpenAI, avec recherche web
 * pour les questions de tendances, de concurrence ou de fournisseurs.
 */
import { env } from '../../config/env.js';
import type { Address, Restaurant } from '../../generated/prisma/client.js';
import { badGateway, badRequest, serviceUnavailable } from '../../lib/http-error.js';
import {
  consumeAiQuota,
  ensureAiRequestWithinLimits,
  estimateTextTokens,
  getSubscriptionUsage,
  MAX_OUTPUT_TOKENS_PER_REQUEST,
} from '../subscriptions/subscriptions.service.js';
import { buildRestaurantContext, pyRegex, toIsoCountryCode } from './ai-context.js';
import type { AIChatMessage, AIChatRequest } from './ai.schemas.js';
import { addConversationMessage, getConversation } from './conversations.service.js';

const OPENAI_RESPONSES_URL = 'https://api.openai.com/v1/responses';
const HTTP_TIMEOUT_MS = 45_000;

type AiRestaurant = Restaurant & { address: Address | null };

/* ---------- Recherche web et cache ---------- */

const WEB_SEARCH_TRIGGER_PATTERNS = [
  String.raw`\bmodifier\b.*\b(carte|menu)\b`,
  String.raw`\bchanger\b.*\b(carte|menu)\b`,
  String.raw`\bajout(?:er|e|ons)?\b.*\b(produit|plat|dessert|boisson|entree|entrée|menu|carte)\b`,
  String.raw`\bnouveau\b.*\b(produit|plat|dessert|boisson|menu)\b`,
  String.raw`\blancer\b.*\b(produit|plat|dessert|boisson|menu)\b`,
  String.raw`\bquel\b.*\b(dessert|boisson|plat|produit)\b.*\b(lancer|ajouter)\b`,
  String.raw`\bqu[ea] ?peut[- ]?on ajouter\b.*\b(carte|menu)?\b`,
  String.raw`\btendance(?:s)?\b`,
  String.raw`\bactuel(?:le|les)?\b`,
  String.raw`\ben ce moment\b`,
  String.raw`\bsaisonn(?:ier|iere|iers|ieres|alité|alite)\b`,
  String.raw`\bfournisseur(?:s)?\b`,
  String.raw`\bgrossiste(?:s)?\b`,
  String.raw`\bdans le coin\b`,
  String.raw`\b[aà] proximit[eé]\b`,
  String.raw`\bconcurren(?:ce|ts?)\b`,
  String.raw`\bautour de nous\b`,
].map((pattern) => pyRegex(pattern));

const WEB_SEARCH_CACHE_TTL_MS = 6 * 60 * 60 * 1000;

const SEARCH_TOPIC_STOPWORDS = new Set([
  'a', 'au', 'aux', 'avec', 'ce', 'ces', 'coherent', 'coherente', 'cohérent', 'cohérente',
  'comment', 'dans', 'de', 'des', 'du', 'en', 'est', 'et', 'faut', 'il', 'la', 'le', 'les',
  'lancer', 'leur', 'local', 'locale', 'locales', 'locaux', 'ma', 'mes', 'modifier', 'mon',
  'notre', 'nos', 'ou', 'par', 'peut', 'plus', 'pour', 'produit', 'produits', 'proximite',
  'proximité', 'quel', 'quelle', 'quelles', 'quels', 'que', 'restaurant', 'sa', 'ses', 'sur',
  'tendance', 'tendances', 'un', 'une', 'vendre', 'vers', 'voici', 'carte', 'menu',
]);

const INVALID_WEB_CACHE_PATTERNS = [
  'nous n’avons pas de recherche web locale active',
  "nous n'avons pas de recherche web locale active",
  'sans recherche web locale',
  'il nous faut une recherche web locale',
  'je ne peux pas sortir des noms',
];

/** Réponses récentes obtenues avec recherche web, par restaurant et par sujet (en mémoire, 6 h). */
const webSearchCache = new Map<string, { answer: string; createdAt: number }>();

const normalizeSearchText = (value: string) =>
  value.toLowerCase().replace(/[^\p{L}\p{N}_\s]/gu, ' ').replace(/\s+/gu, ' ').trim();

const topicTokens = (message: string) =>
  new Set(normalizeSearchText(message).split(' ').filter((token) => token.length >= 3 && !SEARCH_TOPIC_STOPWORDS.has(token)));

const cacheKey = (restaurantId: number, message: string) => {
  const topic = [...topicTokens(message)].sort().join(' ');
  return `${restaurantId}:${topic || normalizeSearchText(message)}`;
};

const isInvalidCachedAnswer = (answer: string) => {
  const normalized = answer.trim().toLowerCase();
  return INVALID_WEB_CACHE_PATTERNS.some((pattern) => normalized.includes(pattern));
};

const getCachedWebContext = (restaurantId: number, message: string) => {
  const key = cacheKey(restaurantId, message);
  const entry = webSearchCache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.createdAt > WEB_SEARCH_CACHE_TTL_MS || isInvalidCachedAnswer(entry.answer)) {
    webSearchCache.delete(key);
    return null;
  }
  return entry.answer;
};

const setCachedWebContext = (restaurantId: number, message: string, answer: string) => {
  if (isInvalidCachedAnswer(answer)) return;
  webSearchCache.set(cacheKey(restaurantId, message), { answer, createdAt: Date.now() });
};

const shouldUseWebSearch = (message: string) => {
  const normalized = message.trim().toLowerCase();
  return Boolean(normalized) && WEB_SEARCH_TRIGGER_PATTERNS.some((pattern) => pattern.test(normalized));
};

const webSearchTool = (restaurant: AiRestaurant) => {
  const city = restaurant.address?.city ? restaurant.address.city.trim() : null;
  const country = toIsoCountryCode(restaurant.address?.country);
  const location: Record<string, string> = { type: 'approximate', timezone: restaurant.timezone };
  if (city) {
    location.city = city;
    location.region = city;
  }
  if (country) location.country = country;
  return { type: 'web_search', user_location: location };
};

/* ---------- Prompt ---------- */

const SYSTEM_PROMPT = [
  "Tu es le bras droit du restaurateur et tu parles comme un membre interne de l'equipe.",
  "Tu utilises 'nous', 'notre', 'nos' et jamais 'vous' pour parler du restaurant.",
  'Tu reponds uniquement dans le cadre du restaurant fourni.',
  'Tu t\'appuies en priorite sur tout le catalogue, toutes les analytics et le contexte du restaurant.',
  'Tu dois tenir compte du style culinaire observe dans la carte actuelle, des categories existantes, des produits deja vendus, de la saison en cours et de la localisation.',
  'Quand une recherche web est disponible, utilise-la pour capter les tendances actuelles, la concurrence locale et les pistes fournisseurs utiles a la decision.',
  "Tu dois aussi analyser la construction de carte: ce qui manque aujourd'hui, ce qui peut completer l'offre et ce qui peut faire monter le panier moyen.",
  'La localisation inclut la ville, le code postal, le pays et les signaux geographiques fournis. Utilise-les pour raisonner sur les produits plausibles localement, par exemple une logique bord de mer, montagne ou interieur, mais seulement si cela reste coherent avec notre carte actuelle.',
  "Si nous proposons un nouveau produit, il doit rester coherent avec l'identite de la carte. Ne suggere jamais un plat hors univers du restaurant.",
  'Ne suggere pas un produit saisonnier incoherent avec la saison actuelle ni un produit qui contredit clairement les habitudes de la carte existante.',
  'Le contexte geographique peut renforcer une recommandation, mais il ne doit jamais suffire a lui seul a justifier un produit qui ne correspond pas deja a notre style culinaire.',
  "Si la carte a un manque structurel evident, par exemple aucune boisson ou aucun dessert autour de plats principaux, priorise d'abord ce manque avant de proposer une simple variante d'un produit deja present.",
  'Tu peux proposer des idees de produits, de carte, de saisonnalite ou de localisation, mais tu dois les presenter comme des recommandations business et non comme des faits certains si les donnees ne prouvent pas directement le point.',
  'Quand nous recommandons une nouveaute, explique brievement pourquoi elle colle a notre carte et a nos ventes.',
  'Si la question porte sur un nouveau plat ou une extension de carte, appuie-toi explicitement sur les categories, produits et tendances deja visibles dans nos donnees.',
  'Quand plusieurs pistes sont possibles, donne au maximum 2 recommandations prioritaires, pas plus.',
  'Commence par la meilleure recommandation, puis eventuellement une deuxieme si elle est vraiment utile.',
  'Ne liste pas 4 ou 5 idees. Ne pars pas dans plusieurs directions a la fois.',
  "Pour une demande de modification de carte, d'ajout produit, de dessert ou boisson a lancer, de fournisseurs ou de concurrence locale, utilise la recherche web si elle est disponible afin de completer nos donnees internes avec de l'information actuelle.",
  "Pour une demande de concurrents, de fournisseurs ou d'acteurs locaux, cite au maximum 2 resultats pour commencer.",
  "Si des fournisseurs peuvent aider, propose seulement des pistes credibles et prudentes: types de fournisseurs, grossistes specialises ou importateurs a valider localement. N'invente jamais de partenariat confirme ni d'information fournisseur non verifiee.",
  "Ne donne jamais de nom, d'adresse ou de coordonnees precises de fournisseur si ces informations ne sont pas presentes dans le contexte fourni. Si nous voulons des fournisseurs nommes et localises, dis clairement qu'une recherche web ou annuaire verifie est necessaire.",
  'Si tu mentionnes des fournisseurs, fais-le de facon breve et uniquement en lien direct avec la recommandation principale.',
  'Si une question depasse les donnees disponibles, dis-le clairement puis propose des hypotheses utiles.',
  "N'invente jamais de chiffres.",
  'Reponds dans la langue du client, avec un ton professionnel, concret, fluide et naturel.',
  'Va droit au but.',
  'Les reponses doivent etre courtes et utiles. Vise une reponse compacte en 3 a 6 phrases dans la plupart des cas.',
  "N'utilise pas de titres automatiques comme 'Reponse courte', 'Pourquoi' ou 'Action conseillee' sauf si c'est vraiment utile.",
  "N'utilise pas de markdown decoratif.",
  "N'utilise pas de listes a puces sauf si la question demande explicitement une liste.",
  "N'utilise pas de texte en gras, donc pas de **...**.",
  "Ne mets jamais d'URL, de lien source ou de site web dans la reponse sauf si on te les demande explicitement.",
  "N'ecris pas 'je vous conseille', 'je vous recommande' ou 'vous devriez'. Prefere des formulations comme 'nous pouvons', 'nous avons interet a', 'notre meilleure piste est'.",
  'Fais des paragraphes compacts dans un texte continu, sans sauts de ligne inutiles.',
  'Ecris comme dans une vraie conversation avec un restaurateur.',
]
  .map((line) => `${line}\n`)
  .join('');

/** json.dumps(…, ensure_ascii=True) : séparateurs « , » et « : », caractères non ASCII échappés. */
const pyJsonDumps = (value: unknown): string => {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'string') return JSON.stringify(value).replace(/[^\x00-\x7f]/g, (char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, '0')}`);
  if (typeof value === 'number' || typeof value === 'boolean') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(pyJsonDumps).join(', ')}]`;
  return `{${Object.entries(value as Record<string, unknown>)
    .map(([key, item]) => `${pyJsonDumps(key)}: ${pyJsonDumps(item)}`)
    .join(', ')}}`;
};

const serializeHistory = (history: AIChatMessage[]) =>
  history
    .slice(-8)
    .map((message) => ({ role: message.role.trim().toLowerCase(), content: message.content.trim() }))
    .filter((message) => message.role === 'user' || message.role === 'assistant');

const buildUserInput = (message: string, history: AIChatMessage[], context: unknown, cachedWebContext: string | null) => {
  const extra = cachedWebContext ? `\n\nContexte cache utile a reutiliser:\n${cachedWebContext}` : '';
  return (
    `Question du restaurateur:\n${message.trim()}\n\n` +
    `Historique recent:\n${pyJsonDumps(serializeHistory(history))}\n\n` +
    `Contexte restaurant:\n${pyJsonDumps(context)}${extra}`
  );
};

/* ---------- Réponse d'OpenAI ---------- */

interface OpenAiResponse {
  output_text?: unknown;
  output?: { type?: string; content?: { text?: unknown }[] }[];
  usage?: { input_tokens?: number; output_tokens?: number; total_tokens?: number };
  error?: { message?: string };
}

const extractOutputText = (response: OpenAiResponse) => {
  if (typeof response.output_text === 'string' && response.output_text.trim()) return response.output_text.trim();
  const texts: string[] = [];
  for (const item of response.output ?? []) {
    for (const content of item.content ?? []) {
      if (typeof content.text === 'string' && content.text.trim()) texts.push(content.text.trim());
    }
  }
  return texts.join('\n').trim();
};

/** Retire le gras, les liens et les URL que le modèle ajoute malgré les consignes. */
const normalizeAnswerText = (answer: string) =>
  answer
    .replaceAll('**', '')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '$1')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/\(\s*[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:\s*[^)]*)?\)/g, '')
    .replace(/\(\s*\)/g, '')
    .replace(/\s+/g, ' ')
    .trim();

const extractUsage = (response: OpenAiResponse) => {
  const inputTokens = Math.trunc(Number(response.usage?.input_tokens ?? 0) || 0);
  const outputTokens = Math.trunc(Number(response.usage?.output_tokens ?? 0) || 0);
  let totalTokens = Math.trunc(Number(response.usage?.total_tokens ?? inputTokens + outputTokens) || 0);
  if (totalTokens <= 0) totalTokens = inputTokens + outputTokens;
  return { inputTokens, outputTokens, totalTokens };
};

const usedWebSearch = (response: OpenAiResponse) => (response.output ?? []).some((item) => item.type === 'web_search_call');

/* ---------- Génération ---------- */

interface GenerateOptions {
  forceWebSearch?: boolean;
  persistConversation?: boolean;
  consumeQuota?: boolean;
}

const generate = async (restaurant: AiRestaurant, payload: AIChatRequest, options: GenerateOptions = {}) => {
  const { forceWebSearch = false, persistConversation = true, consumeQuota = true } = options;
  if (!env.OPENAI_API_KEY) throw serviceUnavailable('OPENAI_API_KEY is not configured');

  const context = await buildRestaurantContext(restaurant);
  const conversationId = payload.conversation_id ?? null;
  const conversation = conversationId !== null ? await getConversation(restaurant.id, conversationId) : null;
  // L'historique vient de la conversation enregistrée (celui envoyé par l'application est ignoré, comme en Python).
  const history = conversation
    ? conversation.messages.slice(-8).filter((message) => message.role === 'user' || message.role === 'assistant')
    : [];

  const webSearch = forceWebSearch || shouldUseWebSearch(payload.message);
  const cachedWebContext = webSearch && !forceWebSearch ? getCachedWebContext(restaurant.id, payload.message) : null;
  const userInput = buildUserInput(payload.message, history, context, cachedWebContext);
  const estimatedInputTokens = estimateTextTokens(SYSTEM_PROMPT) + estimateTextTokens(userInput);

  if (conversationId !== null && consumeQuota) await ensureAiRequestWithinLimits(restaurant, estimatedInputTokens, MAX_OUTPUT_TOKENS_PER_REQUEST);

  const attachWebSearch = webSearch && cachedWebContext === null;
  const model = attachWebSearch ? env.OPENAI_WEB_SEARCH_MODEL : env.OPENAI_MODEL;
  const body: Record<string, unknown> = {
    model,
    input: [
      { role: 'system', content: [{ type: 'input_text', text: SYSTEM_PROMPT }] },
      { role: 'user', content: [{ type: 'input_text', text: userInput }] },
    ],
    max_output_tokens: MAX_OUTPUT_TOKENS_PER_REQUEST,
  };
  if (attachWebSearch) {
    body.tools = [webSearchTool(restaurant)];
    body.tool_choice = 'required';
  }

  const response = await fetch(OPENAI_RESPONSES_URL, {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
  });
  const text = await response.text();
  if (response.status >= 400) {
    let detail: string | null = null;
    try {
      detail = (JSON.parse(text) as OpenAiResponse).error?.message ?? null;
    } catch {
      detail = text.trim() || null;
    }
    throw badGateway(detail || 'OpenAI request failed');
  }

  const json = JSON.parse(text) as OpenAiResponse;
  const searched = usedWebSearch(json);
  const answer = normalizeAnswerText(extractOutputText(json));
  if (!answer) throw badGateway('OpenAI returned an empty answer');
  if (webSearch && searched) setCachedWebContext(restaurant.id, payload.message, answer);

  let { inputTokens, outputTokens, totalTokens } = extractUsage(json);
  if (totalTokens <= 0) {
    totalTokens = estimatedInputTokens + MAX_OUTPUT_TOKENS_PER_REQUEST;
    inputTokens = estimatedInputTokens;
    outputTokens = MAX_OUTPUT_TOKENS_PER_REQUEST;
  }

  if (conversation && persistConversation) {
    await addConversationMessage(conversation.id, { role: 'user', content: payload.message.trim() });
    await addConversationMessage(conversation.id, {
      role: 'assistant',
      content: answer,
      input_tokens: inputTokens,
      output_tokens: outputTokens,
      total_tokens: totalTokens,
    });
  }

  const usageRestaurant = conversationId !== null && consumeQuota ? await consumeAiQuota(restaurant, 1, totalTokens) : restaurant;
  const usage = await getSubscriptionUsage(usageRestaurant);

  return {
    response: {
      conversation_id: conversation?.id ?? 0,
      answer,
      model,
      usage: {
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        total_tokens: totalTokens,
        remaining_messages: usage.usage_remaining,
        remaining_tokens: usage.token_usage_remaining,
      },
    },
    debug: {
      forced_web_search: forceWebSearch,
      should_use_web_search: webSearch,
      used_cached_web_context: cachedWebContext !== null,
      selected_model: model,
      tool_choice: attachWebSearch ? 'required' : null,
      web_search_tool_attached: attachWebSearch,
      used_web_search_tool: searched,
    },
  };
};

export const generateRestaurantAiResponse = async (restaurant: AiRestaurant, payload: AIChatRequest) => {
  if (payload.conversation_id == null) throw badRequest('conversation_id is required');
  return (await generate(restaurant, payload)).response;
};

/** Test de la recherche web : toujours activée, sans enregistrement ni décompte du quota. */
export const debugRestaurantAiWebSearch = (restaurant: AiRestaurant, payload: AIChatRequest) =>
  generate(restaurant, payload, { forceWebSearch: true, persistConversation: false, consumeQuota: false });

