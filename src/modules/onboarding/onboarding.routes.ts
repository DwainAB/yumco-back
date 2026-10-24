/**
 * Routes du questionnaire du cockpit.
 *
 * - `/onboarding/forms/:token…` : publiques, appelées par la page du questionnaire avec le jeton du lien.
 * - le reste : réservé au cockpit (en-tête `x-cockpit-key`).
 */
import { randomUUID, timingSafeEqual } from 'node:crypto';
import type { NextFunction, Request, Response } from 'express';
import { Router } from 'express';
import multer from 'multer';
import { env } from '../../config/env.js';
import { HttpError, unauthorized, serviceUnavailable } from '../../lib/http-error.js';
import { intParams, RequestValidationError, validateRequest, z } from '../../lib/validation.js';
import { uploadImage } from '../uploads/cloudinary.service.js';
import { CockpitRestaurantCreate, CredentialsSend, InvitationCreate, QuestionnaireAnswers, SiteUpdate, SubscriptionPlan } from './onboarding.schemas.js';
import {
  cancelInvitation,
  createFromCockpit,
  createInvitation,
  findOpenInvitation,
  getSite,
  listInvitations,
  listSubmissions,
  markImported,
  platformUrl,
  registerUpload,
  sendCredentials,
  submitInvitation,
  updateSite,
} from './onboarding.service.js';

export const onboardingRouter = Router();

const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

/* ---------- Accès du cockpit ---------- */

const sameSecret = (a: string, b: string) => {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
};

const cockpitOnly = (req: Request, _res: Response, next: NextFunction) => {
  if (!env.COCKPIT_API_KEY) throw serviceUnavailable('COCKPIT_API_KEY is not configured');
  const key = req.header('x-cockpit-key');
  if (!key || !sameSecret(key, env.COCKPIT_API_KEY)) throw unauthorized('Invalid cockpit key');
  next();
};

/* ---------- Réponses ---------- */

type InvitationRow = Awaited<ReturnType<typeof listInvitations>>[number];

const toInvitationResponse = (invitation: InvitationRow) => ({
  id: invitation.id,
  subscription_plan: invitation.subscription_plan,
  recipient_email: invitation.recipient_email,
  status: invitation.status,
  restaurant_id: invitation.restaurant_id,
  restaurant_name: invitation.restaurant?.name ?? null,
  expires_at: invitation.expires_at,
  submitted_at: invitation.submitted_at,
  imported_at: invitation.imported_at,
  created_at: invitation.created_at,
});

const tokenParam = z.object({ token: z.string().min(20).max(100) });
const idParam = intParams('id');
const restaurantParam = intParams('restaurant_id');

/* ---------- Questionnaire public ---------- */

onboardingRouter.get('/onboarding/forms/:token', async (req, res) => {
  const { params } = validateRequest(req, { params: tokenParam });
  const invitation = await findOpenInvitation(params.token);
  res.json({ status: 'open', recipient_email: invitation.recipient_email, expires_at: invitation.expires_at });
});

/** Type réel d'après les premiers octets : l'extension et le type annoncé ne comptent pas. */
const sniffImage = (buf: Buffer): 'png' | 'jpg' | 'webp' | null => {
  if (buf.length >= 8 && buf.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return 'png';
  if (buf.length >= 3 && buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return 'jpg';
  if (buf.length >= 12 && buf.toString('ascii', 0, 4) === 'RIFF' && buf.toString('ascii', 8, 12) === 'WEBP') return 'webp';
  return null;
};

const receiveImage = multer({ storage: multer.memoryStorage(), limits: { fileSize: MAX_UPLOAD_BYTES, files: 1 } }).single('file');

onboardingRouter.post(
  '/onboarding/forms/:token/uploads',
  async (req, res, next) => {
    // Lien vérifié avant de lire le fichier.
    const { params } = validateRequest(req, { params: tokenParam });
    res.locals.invitationId = (await findOpenInvitation(params.token)).id;
    next();
  },
  (req, res, next) =>
    receiveImage(req, res, (error: unknown) => {
      if (error instanceof multer.MulterError && error.code === 'LIMIT_FILE_SIZE') next(new HttpError(413, 'Image too large (8 MB max)'));
      else next(error);
    }),
  async (req, res) => {
    const file = req.file;
    if (!file) throw new RequestValidationError([{ type: 'missing', loc: ['body', 'file'], msg: 'Field required', input: null }]);
    if (!sniffImage(file.buffer)) throw new HttpError(415, 'Unsupported image format: send a PNG, JPEG or WebP image');
    await registerUpload(res.locals.invitationId as number);
    const url = await uploadImage(file.buffer, 'yumco/onboarding');
    const name = file.originalname.replace(/[^\p{L}\p{N}._ -]/gu, '').slice(0, 200) || 'image';
    res.status(201).json({ id: randomUUID(), url, name });
  },
);

/** Images acceptées dans les réponses publiques : seulement celles envoyées sur notre compte Cloudinary. */
const cloudinaryPrefix = () => `https://res.cloudinary.com/${env.CLOUDINARY_CLOUD_NAME}/image/upload/`;

const assertOwnImages = (answers: QuestionnaireAnswers) => {
  const urls = [answers.logo?.url, ...answers.images.map((img) => img.file.url)].filter((url): url is string => Boolean(url));
  const foreign = urls.findIndex((url) => !url.startsWith(cloudinaryPrefix()));
  if (foreign !== -1) throw new RequestValidationError([{ type: 'value_error', loc: ['body', 'images'], msg: 'Images must be uploaded through this form', input: urls[foreign] }]);
};

onboardingRouter.post('/onboarding/forms/:token/submit', async (req, res) => {
  const { params, body } = validateRequest(req, { params: tokenParam, body: QuestionnaireAnswers });
  const invitation = await findOpenInvitation(params.token);
  assertOwnImages(body);
  const restaurantId = await submitInvitation(invitation.id, SubscriptionPlan.parse(invitation.subscription_plan), body);
  res.status(201).json({ restaurant_id: restaurantId });
});

/* ---------- Cockpit ---------- */

onboardingRouter.post('/onboarding/invitations', cockpitOnly, async (req, res) => {
  const { body } = validateRequest(req, { body: InvitationCreate });
  const { invitation, url, emailSent, emailError } = await createInvitation(body.subscription_plan, body.recipient_email ?? null);
  res.status(201).json({ ...toInvitationResponse({ ...invitation, restaurant: null }), url, email_sent: emailSent, email_error: emailError });
});

onboardingRouter.get('/onboarding/invitations', cockpitOnly, async (_req, res) => {
  res.json((await listInvitations()).map(toInvitationResponse));
});

onboardingRouter.post('/onboarding/invitations/:id/cancel', cockpitOnly, async (req, res) => {
  const { params } = validateRequest(req, { params: idParam });
  await cancelInvitation(params.id);
  res.status(204).end();
});

onboardingRouter.get('/onboarding/submissions', cockpitOnly, async (_req, res) => {
  const submissions = await listSubmissions();
  res.json(
    submissions.map((s) => ({
      ...toInvitationResponse(s),
      answers: s.answers,
      platform_url: s.restaurant_id && s.restaurant ? platformUrl(s.restaurant_id, s.restaurant.name) : null,
    })),
  );
});

onboardingRouter.post('/onboarding/submissions/:id/imported', cockpitOnly, async (req, res) => {
  const { params } = validateRequest(req, { params: idParam });
  await markImported(params.id);
  res.status(204).end();
});

onboardingRouter.post('/onboarding/restaurants', cockpitOnly, async (req, res) => {
  const { body } = validateRequest(req, { body: CockpitRestaurantCreate });
  const restaurantId = await createFromCockpit(body.subscription_plan, body.answers);
  res.status(201).json({ restaurant_id: restaurantId, platform_url: platformUrl(restaurantId, body.answers.name) });
});

onboardingRouter.get('/onboarding/restaurants/:restaurant_id/site', cockpitOnly, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParam });
  const { restaurant: _restaurant, ...site } = await getSite(params.restaurant_id);
  res.json(site);
});

onboardingRouter.patch('/onboarding/restaurants/:restaurant_id/site', cockpitOnly, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParam, body: SiteUpdate });
  res.json(await updateSite(params.restaurant_id, body));
});

onboardingRouter.post('/onboarding/restaurants/:restaurant_id/credentials', cockpitOnly, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParam, body: CredentialsSend });
  const result = await sendCredentials(params.restaurant_id, body.site_url);
  res.json({ restaurant_id: params.restaurant_id, user_id: result.userId, account_created: result.accountCreated, credentials_sent_at: result.site.credentials_sent_at });
});
