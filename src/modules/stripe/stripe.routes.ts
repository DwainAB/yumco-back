/**
 * Stripe Connect, paiement en ligne et webhook Stripe (routes/stripe_connect.py).
 */
import express, { Router } from 'express';
import Stripe from 'stripe';
import { env } from '../../config/env.js';
import { prisma } from '../../db/prisma.js';
import { runInBackground } from '../../lib/background.js';
import { badRequest, notFound } from '../../lib/http-error.js';
import { logger } from '../../lib/logger.js';
import { intParams, py, validateRequest, z } from '../../lib/validation.js';
import { authenticate, currentUser, requireRestaurantOwnerOrAdmin } from '../../middleware/auth.js';
import { notifyNewOrder } from '../notifications/push.service.js';
import { loadEmailOrder, sendOrderConfirmed } from '../orders/order-emails.service.js';
import { OrderCreate } from '../orders/orders.schemas.js';
import {
  buildConnectStatus,
  createAccountLink,
  createConnectedAccount,
  createDashboardLoginLink,
  createDraftOrderCheckoutSession,
  refreshConnectedAccount,
  syncOrderPaymentFromCharge,
  syncOrderPaymentFromCheckout,
} from './stripe-connect.service.js';

const StripeConnectLinkRequest = z.object({
  return_url: py.httpUrl().nullable().optional(),
  refresh_url: py.httpUrl().nullable().optional(),
});

const StripeDraftCheckoutSessionRequest = z.object({
  success_url: py.httpUrl(),
  cancel_url: py.httpUrl(),
  order: OrderCreate,
});

export const stripeRouter = Router();

const restaurantParams = intParams('restaurant_id');

stripeRouter.get('/restaurants/:restaurant_id/stripe/connect', authenticate, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  let restaurant = await requireRestaurantOwnerOrAdmin(params.restaurant_id, currentUser(req));
  if (restaurant.stripe_id) restaurant = await refreshConnectedAccount(restaurant);
  res.json(buildConnectStatus(restaurant));
});

stripeRouter.post('/restaurants/:restaurant_id/stripe/connect/account', authenticate, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  const restaurant = await requireRestaurantOwnerOrAdmin(params.restaurant_id, currentUser(req));
  res.json(buildConnectStatus(await createConnectedAccount(restaurant)));
});

stripeRouter.post('/restaurants/:restaurant_id/stripe/connect/onboarding', authenticate, async (req, res) => {
  // Corps facultatif : sans corps, les URL par défaut sont utilisées.
  req.body ??= {};
  const { params, body } = validateRequest(req, { params: restaurantParams, body: StripeConnectLinkRequest });
  const restaurant = await requireRestaurantOwnerOrAdmin(params.restaurant_id, currentUser(req));
  const link = await createAccountLink(restaurant, body.return_url ?? null, body.refresh_url ?? null);
  res.json({ url: new URL(link.url).href, expires_at: link.expires_at ?? null });
});

stripeRouter.post('/restaurants/:restaurant_id/stripe/connect/dashboard', authenticate, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  const restaurant = await requireRestaurantOwnerOrAdmin(params.restaurant_id, currentUser(req));
  const link = await createDashboardLoginLink(restaurant);
  res.json({ url: new URL(link.url).href, expires_at: null });
});

stripeRouter.post('/restaurants/:restaurant_id/orders/checkout-session', async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: StripeDraftCheckoutSessionRequest });
  const restaurant = await prisma.restaurant.findFirst({ where: { id: params.restaurant_id, is_deleted: false } });
  if (!restaurant) throw notFound('Restaurant not found');
  const config = await prisma.restaurantConfig.findUnique({ where: { restaurant_id: restaurant.id } });
  if (!config?.payment_online) throw badRequest('Online payment is not enabled for this restaurant');

  const session = await createDraftOrderCheckoutSession(restaurant, body.order, body.success_url, body.cancel_url);
  res.json({ checkout_session_id: session.id, checkout_url: new URL(session.url!).href });
});

/** Lit l'événement Stripe : signature vérifiée si STRIPE_WEBHOOK_SECRET est défini. */
const readEvent = (payload: Buffer, signature: string | undefined): Stripe.Event => {
  if (env.STRIPE_WEBHOOK_SECRET) {
    try {
      return Stripe.webhooks.constructEvent(payload, signature ?? '', env.STRIPE_WEBHOOK_SECRET);
    } catch (error) {
      if (error instanceof Stripe.errors.StripeSignatureVerificationError) throw badRequest('Invalid Stripe signature');
      throw badRequest('Invalid Stripe payload');
    }
  }
  // Correction de sécurité : sans secret, un événement non signé pourrait marquer une commande comme payée.
  if (env.STRICT_RESTAURANT_ACCESS) throw badRequest('Invalid Stripe signature');
  try {
    return JSON.parse(payload.toString('utf8')) as Stripe.Event;
  } catch {
    throw badRequest('Invalid Stripe payload');
  }
};

stripeRouter.post('/stripe/webhooks', express.raw({ type: () => true }), async (req, res) => {
  const event = readEvent(Buffer.isBuffer(req.body) ? req.body : Buffer.alloc(0), req.header('stripe-signature'));
  const eventObject = event.data.object as unknown as Record<string, unknown>;
  logger.info({ type: event.type, account: event.account }, '[stripe_webhook] received event');

  if (event.type === 'checkout.session.completed' || event.type === 'checkout.session.async_payment_succeeded') {
    if (eventObject.mode !== 'subscription') {
      const result = await syncOrderPaymentFromCheckout(eventObject);
      if (result?.createdFromPending) {
        const { id, restaurant_id: restaurantId, order_number: orderNumber } = result.order;
        // Confirmation et notification après la réponse : un échec d'e-mail ne doit pas faire rejouer le webhook.
        runInBackground([
          {
            name: 'send_order_confirmed',
            run: async () => {
              const [order, restaurant] = await Promise.all([loadEmailOrder(id), prisma.restaurant.findUnique({ where: { id: restaurantId } })]);
              if (order && restaurant) await sendOrderConfirmed(order, restaurant);
            },
          },
          { name: 'notify_new_order', run: () => notifyNewOrder(restaurantId, orderNumber) },
        ]);
      }
    }
  } else if (event.type === 'checkout.session.async_payment_failed') {
    logger.info({ session_id: eventObject.id }, '[stripe_webhook] async payment failed');
  } else if (event.type === 'charge.succeeded' || event.type === 'charge.refunded') {
    await syncOrderPaymentFromCharge(eventObject);
  }
  res.status(200).end();
});

