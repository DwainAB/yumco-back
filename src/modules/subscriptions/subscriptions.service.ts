/**
 * Formules d'abonnement et quotas de l'assistant IA (subscription_service.py).
 */
import { prisma } from '../../db/prisma.js';
import type { Restaurant } from '../../generated/prisma/client.js';
import { badRequest, forbidden } from '../../lib/http-error.js';
import { datetimeOrNull } from '../../lib/serialize.js';

export const ACTIVE_SUBSCRIPTION_STATUSES = new Set(['active', 'trialing']);

export const PLAN_LIMITS: Record<string, number> = { starter: 0, pro_ai: 150, business_ai: 500 };
export const PLAN_TOKEN_LIMITS: Record<string, number> = { starter: 0, pro_ai: 300_000, business_ai: 1_000_000 };

export const MAX_INPUT_TOKENS_PER_REQUEST = 8_000;
export const MAX_OUTPUT_TOKENS_PER_REQUEST = 1_200;

export const PLAN_UPGRADE_MESSAGES: Record<string, string> = {
  starter: "Passez a l'offre Pro IA pour activer l'assistant IA.",
  pro_ai: "Vous avez atteint votre quota IA mensuel. Passez a l'offre Business IA ou attendez le prochain cycle mensuel.",
  business_ai: 'Vous avez atteint votre quota IA mensuel. Attendez le prochain cycle mensuel.',
};

const CYCLE_DAYS = 30;
const nextCycleStart = (cycleStartedAt: Date) => new Date(cycleStartedAt.getTime() + CYCLE_DAYS * 24 * 3600 * 1000);

const normalizePlan = (plan: string) => {
  const normalized = plan.trim().toLowerCase();
  if (!(normalized in PLAN_LIMITS)) throw new Error(`subscription_plan must be one of: ${Object.keys(PLAN_LIMITS).sort().join(', ')}`);
  return normalized;
};

const upgradeMessage = (plan: string) => PLAN_UPGRADE_MESSAGES[plan] ?? PLAN_UPGRADE_MESSAGES.business_ai;

/** Démarre un nouveau cycle de 30 jours s'il n'y en a pas ou si le précédent est terminé. */
export const ensureAiCycleIsCurrent = async (restaurant: Restaurant): Promise<Restaurant> => {
  if (restaurant.ai_cycle_started_at && Date.now() < nextCycleStart(restaurant.ai_cycle_started_at).getTime()) return restaurant;
  return prisma.restaurant.update({
    where: { id: restaurant.id },
    data: { ai_cycle_started_at: new Date(), ai_usage_count: 0, ai_token_usage_count: 0 },
  });
};

/** Change de formule : quotas mis à jour, cycle relancé si la formule change, HubRise retiré en passant à Starter. */
export const applySubscriptionPlan = async (restaurant: Restaurant, subscriptionPlan: string, cycleStartedAt?: Date | null) => {
  const plan = normalizePlan(subscriptionPlan);
  const previousPlan = restaurant.subscription_plan;
  const data: Partial<Restaurant> = {
    subscription_plan: plan,
    ai_monthly_quota: PLAN_LIMITS[plan],
    ai_monthly_token_quota: PLAN_TOKEN_LIMITS[plan],
  };
  if (cycleStartedAt) Object.assign(data, { ai_cycle_started_at: cycleStartedAt, ai_usage_count: 0, ai_token_usage_count: 0 });
  else if (previousPlan !== plan) Object.assign(data, { ai_cycle_started_at: new Date(), ai_usage_count: 0, ai_token_usage_count: 0 });
  else if (!restaurant.ai_cycle_started_at) data.ai_cycle_started_at = new Date();

  return prisma.$transaction(async (tx) => {
    if (previousPlan !== 'starter' && plan === 'starter') {
      await tx.hubriseConnection.deleteMany({ where: { restaurant_id: restaurant.id } });
    }
    return tx.restaurant.update({ where: { id: restaurant.id }, data });
  });
};

/** État de l'abonnement et des quotas IA (RestaurantSubscriptionUsage). */
export const getSubscriptionUsage = async (current: Restaurant) => {
  const restaurant = await ensureAiCycleIsCurrent(current);
  const usageRemaining = Math.max(restaurant.ai_monthly_quota - restaurant.ai_usage_count, 0);
  const tokenUsageRemaining = Math.max(restaurant.ai_monthly_token_quota - restaurant.ai_token_usage_count, 0);
  const isAiEnabled = restaurant.ai_monthly_quota > 0;
  const isQuotaReached = isAiEnabled && usageRemaining <= 0;
  const isTokenQuotaReached = isAiEnabled && tokenUsageRemaining <= 0;
  const status = restaurant.subscription_status;
  const periodEnd = restaurant.subscription_current_period_ends_at;

  return {
    plan: restaurant.subscription_plan,
    interval: restaurant.subscription_interval,
    subscription_status: status,
    subscription_display_status: status && ACTIVE_SUBSCRIPTION_STATUSES.has(status) ? 'Actif' : 'Inactif',
    subscription_cancel_at_period_end: restaurant.subscription_cancel_at_period_end,
    subscription_current_period_ends_at: datetimeOrNull(periodEnd),
    subscription_next_billing_at: status === 'canceled' ? null : datetimeOrNull(periodEnd),
    has_tablet_rental: restaurant.has_tablet_rental,
    has_printer_rental: restaurant.has_printer_rental,
    monthly_quota: restaurant.ai_monthly_quota,
    usage_count: restaurant.ai_usage_count,
    usage_remaining: usageRemaining,
    monthly_token_quota: restaurant.ai_monthly_token_quota,
    token_usage_count: restaurant.ai_token_usage_count,
    token_usage_remaining: tokenUsageRemaining,
    cycle_started_at: datetimeOrNull(restaurant.ai_cycle_started_at),
    cycle_ends_at: restaurant.ai_cycle_started_at ? datetimeOrNull(nextCycleStart(restaurant.ai_cycle_started_at)) : null,
    is_ai_enabled: isAiEnabled,
    is_quota_reached: isQuotaReached,
    is_token_quota_reached: isTokenQuotaReached,
    upgrade_message: !isAiEnabled || isQuotaReached || isTokenQuotaReached ? (PLAN_UPGRADE_MESSAGES[restaurant.subscription_plan] ?? null) : null,
  };
};

/** Estimation grossière : 1 token ≈ 4 caractères. */
export const estimateTextTokens = (text: string) => {
  const normalized = text.trim();
  return normalized ? Math.max(1, Math.floor((normalized.length + 3) / 4)) : 0;
};

/** Refuse la demande si elle dépasse le quota de messages, la taille maximale ou le quota de tokens. */
export const ensureAiRequestWithinLimits = async (
  current: Restaurant,
  inputTokens: number,
  reservedOutputTokens = MAX_OUTPUT_TOKENS_PER_REQUEST,
) => {
  const restaurant = await ensureAiCycleIsCurrent(current);
  if (restaurant.ai_monthly_quota <= 0) throw forbidden(PLAN_UPGRADE_MESSAGES.starter);
  if (restaurant.ai_usage_count + 1 > restaurant.ai_monthly_quota) throw forbidden(upgradeMessage(restaurant.subscription_plan));
  if (inputTokens > MAX_INPUT_TOKENS_PER_REQUEST) throw badRequest('Votre question est trop longue. Reduisez le message avant de reessayer.');
  if (restaurant.ai_token_usage_count + inputTokens + reservedOutputTokens > restaurant.ai_monthly_token_quota) {
    throw forbidden(upgradeMessage(restaurant.subscription_plan));
  }
  return restaurant;
};

/** Décompte un message et ses tokens. */
export const consumeAiQuota = async (current: Restaurant, messageAmount = 1, tokenAmount = 0) => {
  const restaurant = await ensureAiCycleIsCurrent(current);
  if (restaurant.ai_monthly_quota <= 0) throw forbidden(PLAN_UPGRADE_MESSAGES.starter);
  if (restaurant.ai_usage_count + messageAmount > restaurant.ai_monthly_quota) throw forbidden(upgradeMessage(restaurant.subscription_plan));
  if (restaurant.ai_token_usage_count + tokenAmount > restaurant.ai_monthly_token_quota) throw forbidden(upgradeMessage(restaurant.subscription_plan));
  return prisma.restaurant.update({
    where: { id: restaurant.id },
    data: { ai_usage_count: { increment: messageAmount }, ai_token_usage_count: { increment: tokenAmount } },
  });
};
