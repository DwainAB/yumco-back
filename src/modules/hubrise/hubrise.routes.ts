/**
 * Connexion HubRise, retour OAuth et webhook (routes/hubrise.py).
 */
import express, { Router } from 'express';
import { env } from '../../config/env.js';
import { prisma } from '../../db/prisma.js';
import { runInBackground } from '../../lib/background.js';
import { forbidden, HttpError, internalError, notFound, unauthorized } from '../../lib/http-error.js';
import { logger } from '../../lib/logger.js';
import { datetimeOrNull } from '../../lib/serialize.js';
import { intParams, validateRequest } from '../../lib/validation.js';
import { authenticate, currentUser, type CurrentUser } from '../../middleware/auth.js';
import { loadEmailOrder, sendOrderCancelled, sendOrderCompleted, sendOrderPreparing } from '../orders/order-emails.service.js';
import {
  applyHubriseOrderUpdate,
  exchangeCodeForTokens,
  parseRestaurantIdFromState,
  registerHubriseOrderCallback,
  saveHubriseConnection,
  verifyHubriseSignature,
} from './hubrise.service.js';

/** État de la connexion HubRise et de la dernière commande synchronisée (RestaurantHubriseStatusResponse). */
export const hubriseStatus = async (restaurantId: number) => {
  const connection = await prisma.hubriseConnection.findUnique({ where: { restaurant_id: restaurantId } });
  const [lastOrder] = await prisma.$queryRaw<
    { id: number; hubrise_order_id: string; hubrise_raw_status: string | null; hubrise_sync_status: string | null; hubrise_last_error: string | null; hubrise_synced_at: Date | null }[]
  >`
    SELECT id, hubrise_order_id, hubrise_raw_status, hubrise_sync_status, hubrise_last_error, hubrise_synced_at
    FROM orders WHERE restaurant_id = ${restaurantId} AND hubrise_order_id IS NOT NULL
    ORDER BY hubrise_synced_at DESC NULLS LAST, id DESC LIMIT 1`;
  return {
    connected: connection !== null,
    restaurant_id: restaurantId,
    hubrise_account_id: connection?.hubrise_account_id ?? null,
    hubrise_location_id: connection?.hubrise_location_id ?? null,
    token_type: connection?.token_type ?? null,
    scope: connection?.scope ?? null,
    last_order_id: lastOrder?.id ?? null,
    last_hubrise_order_id: lastOrder?.hubrise_order_id ?? null,
    last_hubrise_raw_status: lastOrder?.hubrise_raw_status ?? null,
    last_hubrise_sync_status: lastOrder?.hubrise_sync_status ?? null,
    last_hubrise_error: lastOrder?.hubrise_last_error ?? null,
    last_hubrise_synced_at: datetimeOrNull(lastOrder?.hubrise_synced_at),
  };
};

/** Restaurant non supprimé auquel l'utilisateur est rattaché (ou admin). */
const accessibleRestaurant = async (restaurantId: number, user: CurrentUser) => {
  const restaurant = await prisma.restaurant.findFirst({ where: { id: restaurantId, is_deleted: false } });
  if (!restaurant) throw notFound('Restaurant not found');
  const hasAccess = user.is_admin || (await prisma.role.findFirst({ where: { restaurant_id: restaurantId, user_id: user.id } })) !== null;
  if (!hasAccess) throw forbidden('Not authorized for this restaurant');
  return restaurant;
};

const resultUrl = (status: string, restaurantId: number | null, message?: string) => {
  const redirectUri = env.HUBRISE_RESULT_REDIRECT_URI;
  if (!redirectUri) throw internalError('HUBRISE_RESULT_REDIRECT_URI must be configured for HubRise redirects');
  const params = new URLSearchParams({ status });
  if (restaurantId !== null) params.set('restaurant_id', String(restaurantId));
  if (message) params.set('message', message);
  return `${redirectUri}${redirectUri.includes('?') ? '&' : '?'}${params.toString()}`;
};

export const hubriseRouter = Router();

const restaurantParams = intParams('restaurant_id');

hubriseRouter.get('/restaurants/:restaurant_id/hubrise/status', authenticate, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  await accessibleRestaurant(params.restaurant_id, currentUser(req));
  res.json(await hubriseStatus(params.restaurant_id));
});

hubriseRouter.delete('/restaurants/:restaurant_id/hubrise/connection', authenticate, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  await accessibleRestaurant(params.restaurant_id, currentUser(req));
  const connection = await prisma.hubriseConnection.findUnique({ where: { restaurant_id: params.restaurant_id } });
  if (!connection) throw notFound('HubRise is not connected for this restaurant');
  await prisma.hubriseConnection.delete({ where: { id: connection.id } });
  res.status(204).end();
});

/** Retour du parcours OAuth HubRise : redirection vers l'application avec le résultat. */
hubriseRouter.get('/integrations/hubrise/callback', async (req, res) => {
  const code = typeof req.query.code === 'string' ? req.query.code : undefined;
  const state = typeof req.query.state === 'string' ? req.query.state : undefined;
  let restaurantId: number | null = null;
  let target: string;
  try {
    restaurantId = parseRestaurantIdFromState(state);
    if (!code) throw new HttpError(400, 'Missing code');
    const tokens = await exchangeCodeForTokens(code);
    const connection = await saveHubriseConnection(restaurantId, tokens);
    await registerHubriseOrderCallback(connection);
    target = resultUrl('success', restaurantId, 'HubRise connection saved');
  } catch (error) {
    const message = error instanceof HttpError ? String(error.detail) : 'Unexpected HubRise callback error';
    if (!(error instanceof HttpError)) logger.error({ err: error }, '[hubrise] callback error');
    target = resultUrl('error', restaurantId, message);
  }
  res.redirect(303, target);
});

/** Changement de statut d'une commande dans la caisse. */
hubriseRouter.post('/integrations/hubrise/webhook', express.raw({ type: () => true }), async (req, res) => {
  const rawBody = Buffer.isBuffer(req.body) ? req.body : Buffer.alloc(0);
  if (!verifyHubriseSignature(rawBody, req.header('x-hubrise-hmac-sha256'))) throw unauthorized('Invalid HubRise signature');

  const payload = JSON.parse(rawBody.toString('utf8'));
  logger.info({ payload }, '[hubrise] webhook received');
  const result = await applyHubriseOrderUpdate(payload);
  if (result && result.currentStatus !== result.previousStatus) {
    const { order, currentStatus } = result;
    const senders = { preparing: sendOrderPreparing, completed: sendOrderCompleted, cancelled: sendOrderCancelled } as Record<string, typeof sendOrderCompleted | undefined>;
    const send = currentStatus ? senders[currentStatus] : undefined;
    if (send) {
      runInBackground([
        {
          name: `hubrise_status_email_${currentStatus}`,
          run: async () => {
            const [emailOrder, restaurant] = await Promise.all([
              loadEmailOrder(order.id),
              prisma.restaurant.findUnique({ where: { id: order.restaurant_id }, include: { config: true } }),
            ]);
            if (emailOrder && restaurant) await send(emailOrder, restaurant);
          },
        },
      ]);
    }
  }
  res.status(200).end();
});
