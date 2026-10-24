/**
 * Codes promo des restaurants (promo_code_service.py).
 */
import { prisma, type DbClient } from '../../db/prisma.js';
import type { RestaurantPromoCode } from '../../generated/prisma/client.js';
import { badRequest, conflict, notFound } from '../../lib/http-error.js';
import { Decimal, minDecimal, money } from '../../lib/money.js';

export const normalizeCode = (code: string) => code.trim().toUpperCase();

export const getPromoCodeById = (restaurantId: number, promoCodeId: number) =>
  prisma.restaurantPromoCode.findFirst({ where: { id: promoCodeId, restaurant_id: restaurantId } });

export const listPromoCodes = (restaurantId: number) =>
  prisma.restaurantPromoCode.findMany({ where: { restaurant_id: restaurantId }, orderBy: [{ created_at: 'desc' }, { id: 'desc' }] });

export const getPromoCodeByCode = (restaurantId: number, code: string, db: DbClient = prisma) =>
  db.restaurantPromoCode.findFirst({ where: { restaurant_id: restaurantId, code: normalizeCode(code) }, orderBy: { id: 'asc' } });

/** 409 si un autre code promo du restaurant porte déjà ce code. */
export const ensureUniquePromoCode = async (restaurantId: number, code: string, excludePromoCodeId?: number) => {
  const existing = await prisma.restaurantPromoCode.findFirst({
    where: { restaurant_id: restaurantId, code: normalizeCode(code), ...(excludePromoCodeId !== undefined ? { id: { not: excludePromoCodeId } } : {}) },
  });
  if (existing) throw conflict('Un code promo avec ce code existe deja pour ce restaurant');
};

/** Vérifie le code pour un panier et calcule la remise (au centime, plafonnée au montant du panier). */
export const validatePromoCodeForOrder = async (
  restaurantId: number,
  code: string,
  itemsSubtotal: Decimal,
  db: DbClient = prisma,
): Promise<[RestaurantPromoCode, Decimal]> => {
  const promoCode = await getPromoCodeByCode(restaurantId, code, db);
  if (!promoCode) throw notFound('Code promo introuvable');

  const now = Date.now();
  if (!promoCode.is_active) throw badRequest('Ce code promo est désactivé');
  if (promoCode.start_at && promoCode.start_at.getTime() > now) throw badRequest("Ce code promo n'est pas encore actif");
  if (promoCode.end_at && promoCode.end_at.getTime() < now) throw badRequest('Ce code promo a expiré');
  if (promoCode.usage_limit !== null && (promoCode.usage_count ?? 0) >= promoCode.usage_limit) {
    throw badRequest("Ce code promo a atteint sa limite d'utilisation");
  }

  const subtotal = money(itemsSubtotal);
  if (subtotal.lessThanOrEqualTo(0)) throw badRequest('Le panier doit être supérieur à 0');
  const minimumOrderAmount = money(promoCode.minimum_order_amount ?? 0);
  if (subtotal.lessThan(minimumOrderAmount)) {
    throw badRequest(`Ce code promo est valable à partir de ${minimumOrderAmount.toNumber().toFixed(2)} EUR de commande`);
  }

  const discountValue = money(promoCode.discount_value);
  const discountAmount =
    promoCode.discount_type === 'percent'
      ? subtotal.times(discountValue).dividedBy(100).toDecimalPlaces(2, Decimal.ROUND_HALF_UP)
      : discountValue;
  return [promoCode, minDecimal(subtotal, money(discountAmount))];
};

export const incrementPromoCodeUsage = async (restaurantId: number, code: string, db: DbClient = prisma) => {
  const promoCode = await getPromoCodeByCode(restaurantId, code, db);
  if (promoCode) await db.restaurantPromoCode.update({ where: { id: promoCode.id }, data: { usage_count: { increment: 1 } } });
};
