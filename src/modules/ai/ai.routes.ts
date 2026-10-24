/**
 * Assistant IA et conversations (routes/ai.py).
 */
import { Router, type RequestHandler } from 'express';
import { env } from '../../config/env.js';
import { prisma } from '../../db/prisma.js';
import { notFound } from '../../lib/http-error.js';
import { intParams, validateRequest } from '../../lib/validation.js';
import { authenticate, currentUser, requireRestaurantOwnerOrAdmin } from '../../middleware/auth.js';
import { AI_CONVERSATIONS_PAGE_SIZE, AIChatRequest, AIConversationCreate, AIConversationListQuery } from './ai.schemas.js';
import { debugRestaurantAiWebSearch, generateRestaurantAiResponse } from './ai.service.js';
import { createConversation, getConversation, listConversations, toConversationDetail, toConversationSummary } from './conversations.service.js';

export const aiRouter = Router();

const restaurantParams = intParams('restaurant_id');

/** Restaurant (avec son adresse) si l'utilisateur en est propriétaire, gérant ou admin. */
const ownedRestaurant = async (restaurantId: number, user: Parameters<typeof requireRestaurantOwnerOrAdmin>[1]) => {
  await requireRestaurantOwnerOrAdmin(restaurantId, user);
  return prisma.restaurant.findUniqueOrThrow({ where: { id: restaurantId }, include: { address: true } });
};

aiRouter.post('/restaurants/:restaurant_id/ai/chat', authenticate, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: AIChatRequest });
  const restaurant = await ownedRestaurant(params.restaurant_id, currentUser(req));
  res.json(await generateRestaurantAiResponse(restaurant, body));
});

/** Correction de sécurité : en mode strict, le test de recherche web demande une connexion. */
const authenticateIfStrict: RequestHandler = (req, res, next) => (env.STRICT_RESTAURANT_ACCESS ? authenticate(req, res, next) : next());

/** Test de la recherche web (réservé au propriétaire, au gérant ou à un admin en mode strict ; public en Python). */
aiRouter.post('/restaurants/:restaurant_id/ai/debug/web-search', authenticateIfStrict, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: AIChatRequest });
  const restaurant = env.STRICT_RESTAURANT_ACCESS
    ? await ownedRestaurant(params.restaurant_id, currentUser(req))
    : await prisma.restaurant.findFirst({ where: { id: params.restaurant_id, is_deleted: false }, include: { address: true } });
  if (!restaurant) throw notFound('Restaurant not found');
  const { response, debug } = await debugRestaurantAiWebSearch(restaurant, body);
  res.json({ conversation_id: body.conversation_id ?? null, answer: response.answer, model: response.model, usage: response.usage, debug });
});

aiRouter.post('/restaurants/:restaurant_id/ai/conversations', authenticate, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: AIConversationCreate });
  const user = currentUser(req);
  await requireRestaurantOwnerOrAdmin(params.restaurant_id, user);
  res.status(201).json(toConversationSummary(await createConversation(params.restaurant_id, user.id, body.title)));
});

aiRouter.get('/restaurants/:restaurant_id/ai/conversations', authenticate, async (req, res) => {
  const { params, query } = validateRequest(req, { params: restaurantParams, query: AIConversationListQuery });
  await requireRestaurantOwnerOrAdmin(params.restaurant_id, currentUser(req));
  const { items, total } = await listConversations(params.restaurant_id, query.page, query.q, AI_CONVERSATIONS_PAGE_SIZE);
  res.json({
    items: items.map(toConversationSummary),
    page: query.page,
    page_size: AI_CONVERSATIONS_PAGE_SIZE,
    total_items: total,
    total_pages: Math.max(1, Math.ceil(total / AI_CONVERSATIONS_PAGE_SIZE)),
    query: query.q ? query.q.trim() : null,
  });
});

aiRouter.get('/restaurants/:restaurant_id/ai/conversations/:conversation_id', authenticate, async (req, res) => {
  const { params } = validateRequest(req, { params: intParams('restaurant_id', 'conversation_id') });
  await requireRestaurantOwnerOrAdmin(params.restaurant_id, currentUser(req));
  res.json(toConversationDetail(await getConversation(params.restaurant_id, params.conversation_id)));
});

