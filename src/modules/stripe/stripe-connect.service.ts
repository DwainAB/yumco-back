/**
 * Stripe Connect (comptes Express des restaurants) et paiement en ligne des commandes (stripe_connect_service.py).
 */
import Stripe from 'stripe';
import { env } from '../../config/env.js';
import { prisma } from '../../db/prisma.js';
import type { Restaurant } from '../../generated/prisma/client.js';
import { badRequest, notFound, serviceUnavailable } from '../../lib/http-error.js';
import { logger } from '../../lib/logger.js';
import { toCents } from '../../lib/money.js';
import { OrderCreate, serializeOrderCreate } from '../orders/orders.schemas.js';
import { createOrder } from '../orders/orders.service.js';
import { calculateOrderPricing, computeItemsSubtotal, pricingInclude } from '../orders/pricing.service.js';

/** Même version d'API que le SDK Python (stripe 13.0.1). */
const STRIPE_API_VERSION = '2025-09-30.clover';

let client: Stripe | null = null;

export const stripeClient = () => {
  if (!env.STRIPE_SECRET_KEY) throw serviceUnavailable('Stripe is not configured on the server');
  return (client ??= new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: STRIPE_API_VERSION }));
};

const defaultUrl = (path: string) => {
  const base = env.FRONTEND_BASE_URL || env.APP_BASE_URL;
  if (!base) throw badRequest('A return URL must be provided or FRONTEND_BASE_URL/APP_BASE_URL must be configured');
  return `${base.replace(/\/+$/, '')}${path}`;
};

const accountFlags = (account: Stripe.Account) => ({
  stripe_charges_enabled: Boolean(account.charges_enabled),
  stripe_payouts_enabled: Boolean(account.payouts_enabled),
  stripe_details_submitted: Boolean(account.details_submitted),
});

/** Met à jour l'état du compte Stripe du restaurant (paiements, virements, informations). */
export const refreshConnectedAccount = async (restaurant: Restaurant) => {
  if (!restaurant.stripe_id) throw notFound('Stripe account not found for this restaurant');
  const account = await stripeClient().accounts.retrieve(restaurant.stripe_id);
  return prisma.restaurant.update({ where: { id: restaurant.id }, data: accountFlags(account) });
};

export const createConnectedAccount = async (restaurant: Restaurant) => {
  if (restaurant.stripe_id) return refreshConnectedAccount(restaurant);
  const account = await stripeClient().accounts.create({
    type: 'express',
    country: 'FR',
    email: restaurant.email,
    business_type: 'company',
    capabilities: { card_payments: { requested: true }, transfers: { requested: true } },
    metadata: { restaurant_id: String(restaurant.id), restaurant_name: restaurant.name },
  });
  return prisma.restaurant.update({ where: { id: restaurant.id }, data: { stripe_id: account.id, ...accountFlags(account) } });
};

/** Lien vers le formulaire d'inscription Stripe (le compte est créé s'il n'existe pas). */
export const createAccountLink = async (restaurant: Restaurant, returnUrl: string | null, refreshUrl: string | null) => {
  const updated = await createConnectedAccount(restaurant);
  return stripeClient().accountLinks.create({
    account: updated.stripe_id!,
    refresh_url: refreshUrl || defaultUrl(`/restaurants/${updated.id}/stripe/refresh`),
    return_url: returnUrl || defaultUrl(`/restaurants/${updated.id}/stripe/return`),
    type: 'account_onboarding',
  });
};

export const createDashboardLoginLink = async (restaurant: Restaurant) => {
  const updated = await refreshConnectedAccount(restaurant);
  if (!updated.stripe_id) throw notFound('Stripe account not found for this restaurant');
  return stripeClient().accounts.createLoginLink(updated.stripe_id);
};

export const buildConnectStatus = (restaurant: Restaurant) => ({
  restaurant_id: restaurant.id,
  stripe_account_id: restaurant.stripe_id,
  onboarding_completed: Boolean(restaurant.stripe_details_submitted && restaurant.stripe_charges_enabled && restaurant.stripe_payouts_enabled),
  charges_enabled: restaurant.stripe_charges_enabled,
  payouts_enabled: restaurant.stripe_payouts_enabled,
  details_submitted: restaurant.stripe_details_submitted,
});

/** Total à payer pour une commande pas encore créée (_compute_order_total). */
const computeOrderTotal = async (restaurantId: number, data: OrderCreate) => {
  const restaurant = await prisma.restaurant.findUniqueOrThrow({ where: { id: restaurantId }, include: pricingInclude });
  const itemsSubtotal = await computeItemsSubtotal(restaurantId, data.items);
  const pricing = await calculateOrderPricing({
    restaurant,
    orderType: data.type,
    itemsSubtotal,
    address: data.type === 'delivery' && data.address ? data.address : null,
    promoCode: data.promo_code,
  });
  return pricing.amount_total;
};

/**
 * Paiement en ligne : la commande est gardée en attente et ne sera créée qu'au retour du webhook Stripe.
 */
export const createDraftOrderCheckoutSession = async (restaurant: Restaurant, orderData: OrderCreate, successUrl: string, cancelUrl: string) => {
  const updated = await refreshConnectedAccount(restaurant);
  if (!updated.stripe_id) throw badRequest('Restaurant is not connected to Stripe');
  if (!updated.stripe_charges_enabled) throw badRequest('Restaurant Stripe account is not ready to accept payments');

  const metadata = { restaurant_id: String(updated.id), flow: 'draft_order' };
  const session = await stripeClient().checkout.sessions.create(
    {
      mode: 'payment',
      success_url: successUrl,
      cancel_url: cancelUrl,
      line_items: [
        {
          quantity: 1,
          price_data: {
            currency: 'eur',
            unit_amount: toCents(await computeOrderTotal(updated.id, orderData)),
            product_data: { name: `Commande ${updated.name}`, description: `Commande Yumco pour ${updated.name}` },
          },
        },
      ],
      metadata,
      payment_intent_data: { metadata },
    },
    { stripeAccount: updated.stripe_id },
  );

  await prisma.pendingOnlineOrder.create({
    data: { restaurant_id: updated.id, checkout_session_id: session.id, payload_json: serializeOrderCreate(orderData) },
  });
  return session;
};

type CheckoutPayload = { id?: string; metadata?: Record<string, string> | null; payment_intent?: unknown };

/** Paiement validé : crée la commande en attente (ou marque payée la commande existante). */
export const syncOrderPaymentFromCheckout = async (session: CheckoutPayload) => {
  const metadata = session.metadata ?? {};
  const orderId = metadata.order_id;
  logger.info({ session_id: session.id, order_id: orderId, metadata }, '[stripe_connect] checkout event received');
  const paymentIntent = typeof session.payment_intent === 'string' ? session.payment_intent : null;

  if (!orderId) {
    if (!session.id) {
      logger.info('[stripe_connect] checkout event skipped: missing session id');
      return null;
    }
    const pending = await prisma.pendingOnlineOrder.findFirst({ where: { checkout_session_id: session.id } });
    if (!pending) {
      logger.info({ session_id: session.id }, '[stripe_connect] checkout event skipped: pending order not found');
      return null;
    }
    const order = await createOrder(pending.restaurant_id, OrderCreate.parse(JSON.parse(pending.payload_json)));
    const paid = await prisma.$transaction(async (tx) => {
      const updated = await tx.order.update({
        where: { id: order.id },
        data: { payment_status: 'paid', stripe_checkout_session_id: session.id, stripe_payment_intent_id: paymentIntent },
      });
      await tx.pendingOnlineOrder.delete({ where: { id: pending.id } });
      return updated;
    });
    logger.info({ order_id: paid.id, session_id: session.id }, '[stripe_connect] order created from pending checkout');
    return { order: paid, createdFromPending: true };
  }

  const existing = await prisma.order.findUnique({ where: { id: Number.parseInt(orderId, 10) } });
  if (!existing) {
    logger.info({ order_id: orderId }, '[stripe_connect] checkout event skipped: order not found');
    return null;
  }
  const paid = await prisma.order.update({
    where: { id: existing.id },
    data: { stripe_checkout_session_id: session.id ?? null, stripe_payment_intent_id: paymentIntent, payment_status: 'paid' },
  });
  logger.info({ order_id: paid.id }, '[stripe_connect] existing order marked as paid');
  return { order: paid, createdFromPending: false };
};

type ChargePayload = { id?: string; metadata?: Record<string, string> | null; payment_intent?: unknown; refunded?: boolean };

/** Paiement encaissé ou remboursé. */
export const syncOrderPaymentFromCharge = async (charge: ChargePayload) => {
  const orderId = charge.metadata?.order_id;
  if (!orderId) return;
  const order = await prisma.order.findUnique({ where: { id: Number.parseInt(orderId, 10) } });
  if (!order) return;
  await prisma.order.update({
    where: { id: order.id },
    data: {
      stripe_charge_id: charge.id ?? null,
      stripe_payment_intent_id: typeof charge.payment_intent === 'string' ? charge.payment_intent : null,
      payment_status: charge.refunded ? 'refunded' : 'paid',
    },
  });
};
