/**
 * Codes promo (routes/promo_code.py).
 */
import { Router } from 'express';
import { prisma } from '../../db/prisma.js';
import type { Prisma, RestaurantPromoCode } from '../../generated/prisma/client.js';
import { notFound } from '../../lib/http-error.js';
import { datetime, datetimeOrNull, decimalString, decimalStringOrNull } from '../../lib/serialize.js';
import { intParams, validateRequest } from '../../lib/validation.js';
import { restaurantMember } from '../../middleware/auth.js';
import { calculateOrderPricing, computeItemsSubtotal } from '../orders/pricing.service.js';
import { PromoCodeCreate, PromoCodeUpdate, PromoCodeValidationRequest } from './promo-codes.schemas.js';
import { ensureUniquePromoCode, getPromoCodeById, listPromoCodes } from './promo-codes.service.js';

const toPromoCodeResponse = (promo: RestaurantPromoCode) => ({
  code: promo.code,
  discount_type: promo.discount_type,
  discount_value: decimalString(promo.discount_value),
  minimum_order_amount: decimalStringOrNull(promo.minimum_order_amount),
  usage_limit: promo.usage_limit,
  start_at: datetimeOrNull(promo.start_at),
  end_at: datetimeOrNull(promo.end_at),
  is_active: promo.is_active,
  id: promo.id,
  restaurant_id: promo.restaurant_id,
  usage_count: promo.usage_count,
  created_at: datetime(promo.created_at!),
});

const getRestaurantOr404 = async (restaurantId: number) => {
  const restaurant = await prisma.restaurant.findFirst({ where: { id: restaurantId, is_deleted: false }, include: { address: true, config: true, delivery_tiers: { orderBy: { id: 'asc' } } } });
  if (!restaurant) throw notFound('Restaurant not found');
  return restaurant;
};

export const promoCodesRouter = Router();

const restaurantParams = intParams('restaurant_id');
const promoParams = intParams('restaurant_id', 'promo_code_id');

promoCodesRouter.get('/restaurants/:restaurant_id/promo-codes', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  await getRestaurantOr404(params.restaurant_id);
  res.json((await listPromoCodes(params.restaurant_id)).map(toPromoCodeResponse));
});

promoCodesRouter.post('/restaurants/:restaurant_id/promo-codes', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: PromoCodeCreate });
  await getRestaurantOr404(params.restaurant_id);
  await ensureUniquePromoCode(params.restaurant_id, body.code);
  const promo = await prisma.restaurantPromoCode.create({
    data: {
      restaurant_id: params.restaurant_id,
      code: body.code,
      discount_type: body.discount_type,
      discount_value: body.discount_value,
      minimum_order_amount: body.minimum_order_amount ?? null,
      usage_limit: body.usage_limit ?? null,
      start_at: body.start_at ?? null,
      end_at: body.end_at ?? null,
      is_active: body.is_active,
      usage_count: 0,
    },
  });
  res.status(201).json(toPromoCodeResponse(promo));
});

promoCodesRouter.put('/restaurants/:restaurant_id/promo-codes/:promo_code_id', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: promoParams, body: PromoCodeUpdate });
  await getRestaurantOr404(params.restaurant_id);
  const promo = await getPromoCodeById(params.restaurant_id, params.promo_code_id);
  if (!promo) throw notFound('Code promo introuvable');
  if (body.code) await ensureUniquePromoCode(params.restaurant_id, body.code, promo.id);
  const updated = await prisma.restaurantPromoCode.update({ where: { id: promo.id }, data: body as Prisma.RestaurantPromoCodeUpdateInput });
  res.json(toPromoCodeResponse(updated));
});

promoCodesRouter.delete('/restaurants/:restaurant_id/promo-codes/:promo_code_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: promoParams });
  await getRestaurantOr404(params.restaurant_id);
  const promo = await getPromoCodeById(params.restaurant_id, params.promo_code_id);
  if (!promo) throw notFound('Code promo introuvable');
  await prisma.restaurantPromoCode.delete({ where: { id: promo.id } });
  res.status(204).end();
});

/** Vérification publique d'un code promo pour un panier (plateforme de commande). */
promoCodesRouter.post('/restaurants/:restaurant_id/promo-codes/validate', async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: PromoCodeValidationRequest });
  const restaurant = await getRestaurantOr404(params.restaurant_id);
  const itemsSubtotal = await computeItemsSubtotal(restaurant.id, body.items);
  const pricing = await calculateOrderPricing({
    restaurant,
    orderType: body.type,
    itemsSubtotal,
    address: body.address ?? null,
    promoCode: body.promo_code,
  });
  res.json({
    promo_code: body.promo_code,
    discount_type: String(pricing.discount_type),
    discount_value: Number(pricing.discount_value ?? 0),
    items_subtotal: pricing.items_subtotal.toNumber(),
    discount_amount: pricing.discount_amount.toNumber(),
    discounted_subtotal: pricing.discounted_subtotal.toNumber(),
    delivery_fee: pricing.delivery_fee.toNumber(),
    amount_total: pricing.amount_total.toNumber(),
  });
});
