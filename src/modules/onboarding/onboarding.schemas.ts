/**
 * Questionnaire du cockpit : réponses du restaurateur et demandes du cockpit.
 *
 * Les réponses sont un document du cockpit, gardé tel quel en base (`onboarding_invitations.answers`) : leurs champs sont
 * en camelCase, comme dans le cockpit, contrairement au reste de l'API.
 * Même schéma que `questionnaireAnswers` dans site-automatisation/backend/src/schemas.ts : à modifier ensemble.
 */
import { z } from '../../lib/validation.js';
import { ALLOWED_SUBSCRIPTION_PLANS } from '../restaurants/restaurants.schemas.js';

const text = (max: number) => z.string().trim().min(1).max(max);
const optionalText = (max: number) => z.string().trim().max(max).default('');
const email = z.string().trim().toLowerCase().email().max(254);

const time = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'Heure au format HH:mm');
const service = z.object({ open: time, close: time }).refine((s) => s.open !== s.close, 'Heures d’ouverture et de fermeture identiques').nullable();
const day = z.object({ closed: z.boolean(), lunch: service, dinner: service });

export const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;

const uploadedFile = z.object({ id: text(80), url: text(500), name: z.string().trim().max(200) });

/** Tranche de livraison : de `fromKm` à `toKm`, frais `fee`, gratuite à partir de `freeFrom` € (facultatif). */
const deliveryZone = z
  .object({
    fromKm: z.number().int().min(0).max(100),
    toKm: z.number().int().min(1).max(100),
    fee: z.number().min(0).max(100),
    freeFrom: z.number().positive().max(10_000).nullable(),
  })
  .refine((zone) => zone.toKm > zone.fromKm, { message: 'La distance de fin doit être supérieure à celle de début', path: ['toKm'] });

export const QuestionnaireAnswers = z
  .object({
    name: text(120),
    restaurantType: text(120),
    address: z.object({ street: text(200), postalCode: text(20), city: text(120), country: text(80) }),
    phone: text(40),
    email,
    googleReviewUrl: z.union([z.literal(''), z.string().trim().url().max(500).startsWith('https://')]).default(''),
    manager: z.object({ firstName: text(80), lastName: text(80), email, phone: text(40) }),
    hours: z.object(Object.fromEntries(DAY_KEYS.map((key) => [key, day])) as Record<(typeof DAY_KEYS)[number], typeof day>),
    onsite: z.object({ enabled: z.boolean(), tables: z.number().int().min(0).max(200), seatsPerTable: z.number().int().min(1).max(30) }),
    takesReservations: z.boolean(),
    onlineOrdering: z.boolean(),
    pickup: z.boolean(),
    preparationTime: z.number().int().min(5).max(180),
    delivery: z.object({
      enabled: z.boolean(),
      lunch: z.boolean(),
      dinner: z.boolean(),
      maxKm: z.number().int().min(1).max(100),
      zones: z.array(deliveryZone).max(10),
    }),
    menu: z.object({
      aLaCarte: z.boolean(),
      allYouCanEat: z.boolean(),
      formulas: z.array(z.object({ name: text(80), price: z.number().positive().max(1000) })).max(10),
    }),
    wantsOnlinePayment: z.boolean(),
    customRequests: optionalText(4000),
    logo: uploadedFile.nullable(),
    images: z.array(z.object({ file: uploadedFile, description: text(300) })).max(15),
    branding: z.object({
      colors: z.array(z.string().regex(/^#[0-9a-fA-F]{6}$/, 'Couleur au format #RRGGBB')).max(3),
      font: z.string().trim().max(80).nullable(),
    }),
  })
  .superRefine((a, ctx) => {
    const issue = (message: string, path: (string | number)[]) => ctx.addIssue({ code: 'custom', message, path });

    if (DAY_KEYS.every((key) => a.hours[key].closed)) issue('Le restaurant doit être ouvert au moins un jour', ['hours']);
    for (const key of DAY_KEYS) {
      const d = a.hours[key];
      if (!d.closed && !d.lunch && !d.dinner) issue('Jour ouvert sans service : indiquez le midi, le soir, ou « fermé »', ['hours', key]);
    }
    if (!a.menu.aLaCarte && !a.menu.allYouCanEat) issue('Choisissez « à la carte », « à volonté » ou les deux', ['menu']);
    if (a.menu.allYouCanEat && !a.menu.formulas.length) issue('Ajoutez au moins une formule à volonté', ['menu', 'formulas']);

    if (!a.onlineOrdering) return;
    if (!a.pickup && !a.delivery.enabled) issue('Commande en ligne : choisissez la vente à emporter, la livraison ou les deux', ['onlineOrdering']);
    if (!a.delivery.enabled) return;
    if (!a.delivery.lunch && !a.delivery.dinner) issue('Livraison : choisissez le midi, le soir ou les deux', ['delivery']);
    if (!a.delivery.zones.length) issue('Ajoutez au moins une zone de livraison', ['delivery', 'zones']);
    a.delivery.zones.forEach((zone, index) => {
      if (zone.toKm > a.delivery.maxKm) issue(`La zone dépasse la distance maximale (${a.delivery.maxKm} km)`, ['delivery', 'zones', index, 'toKm']);
      if (zone.freeFrom !== null && zone.fee === 0) issue('Livraison déjà gratuite : retirez le seuil de gratuité', ['delivery', 'zones', index, 'freeFrom']);
    });
    // Même règle que l'application : deux zones ne se chevauchent pas et ne partagent pas de borne.
    const sorted = [...a.delivery.zones].sort((x, y) => x.fromKm - y.fromKm);
    for (let i = 1; i < sorted.length; i += 1) {
      if (sorted[i].fromKm <= sorted[i - 1].toKm) {
        issue('Les zones de livraison ne doivent pas se chevaucher (ex. 0–3 km puis 4–6 km)', ['delivery', 'zones']);
        break;
      }
    }
  });
export type QuestionnaireAnswers = z.output<typeof QuestionnaireAnswers>;

export const SubscriptionPlan = z.enum(ALLOWED_SUBSCRIPTION_PLANS);
export type SubscriptionPlan = z.output<typeof SubscriptionPlan>;

export const InvitationCreate = z.object({
  subscription_plan: SubscriptionPlan,
  /** Facultatif : si présent, le lien est envoyé par e-mail à cette adresse. */
  recipient_email: email.nullable().optional(),
});

/** Questionnaire rempli directement depuis le cockpit (sans lien). */
export const CockpitRestaurantCreate = z.object({ subscription_plan: SubscriptionPlan, answers: QuestionnaireAnswers });

export const SiteUpdate = z.object({
  status: z.enum(['design', 'development', 'online']).optional(),
  site_url: z.string().trim().url().max(500).nullable().optional(),
  repo_url: z.string().trim().url().max(500).nullable().optional(),
});

export const CredentialsSend = z.object({ site_url: z.string().trim().url().max(500).startsWith('https://') });
