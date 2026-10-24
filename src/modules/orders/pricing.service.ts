/**
 * Tarification d'une commande (order_service.py) : sous-total, frais de livraison selon la distance
 * et le montant du panier, remise du code promo.
 */
import { env } from '../../config/env.js';
import { prisma, type DbClient } from '../../db/prisma.js';
import type { DeliveryTier, Prisma } from '../../generated/prisma/client.js';
import { badGateway, badRequest, notFound } from '../../lib/http-error.js';
import { Decimal, maxDecimal, money, ZERO } from '../../lib/money.js';
import { pyRound } from '../../lib/python.js';
import { AddressNotFoundError, geocodeAddress, haversine, type AddressFields } from '../geo/geo.service.js';
import { validatePromoCodeForOrder } from '../promo-codes/promo-codes.service.js';
import type { OrderItemCreate } from './orders.schemas.js';

/** Restaurant avec ce qu'il faut pour calculer une livraison. */
export const pricingInclude = {
  address: true,
  config: true,
  delivery_tiers: { orderBy: { id: 'asc' } },
} as const satisfies Prisma.RestaurantInclude;

export type PricingRestaurant = Prisma.RestaurantGetPayload<{ include: typeof pricingInclude }>;

export const loadPricingRestaurant = (restaurantId: number, db: DbClient = prisma) =>
  db.restaurant.findUnique({ where: { id: restaurantId }, include: pricingInclude });

/* ---------- Articles ---------- */

/**
 * Correction de sécurité : les produits, menus, options et formules doivent appartenir au restaurant.
 * Sans STRICT_RESTAURANT_ACCESS, n'importe quel identifiant est accepté comme en Python.
 */
const ownedBy = (restaurantId: number) => (env.STRICT_RESTAURANT_ACCESS ? { restaurant_id: restaurantId } : {});

export const findProduct = (restaurantId: number, productId: number, db: DbClient = prisma) =>
  db.product.findFirst({ where: { id: productId, ...ownedBy(restaurantId) } });

export const findMenu = (restaurantId: number, menuId: number, db: DbClient = prisma) =>
  db.menu.findFirst({ where: { id: menuId, ...ownedBy(restaurantId) } });

export const findMenuOption = (restaurantId: number, optionId: number, db: DbClient = prisma) =>
  db.menuOption.findFirst({
    where: { id: optionId, ...(env.STRICT_RESTAURANT_ACCESS ? { category: { menu: { restaurant_id: restaurantId } } } : {}) },
  });

export const findAllYouCanEat = (restaurantId: number, offerId: number, db: DbClient = prisma) =>
  db.allYouCanEat.findFirst({ where: { id: offerId, ...ownedBy(restaurantId) } });

/** Une quantité nulle ou négative donnerait un total négatif (correction de sécurité). */
export const assertValidQuantity = (quantity: number) => {
  if (env.STRICT_RESTAURANT_ACCESS && quantity < 1) throw badRequest('Item quantity must be at least 1');
};

export const ITEM_REFERENCE_REQUIRED = 'Each item must have a product_id, menu_id, or all_you_can_eat_id';

/** Sous-total des articles d'un panier (compute_items_subtotal). */
export const computeItemsSubtotal = async (restaurantId: number, items: OrderItemCreate[], db: DbClient = prisma) => {
  let subtotal = new Decimal('0.00');
  for (const item of items) {
    if (item.product_id) {
      assertValidQuantity(item.quantity);
      const product = await findProduct(restaurantId, item.product_id, db);
      if (!product) throw badRequest(`Product ${item.product_id} not found`);
      subtotal = subtotal.plus(money(Number(product.price) * item.quantity));
    } else if (item.menu_id) {
      assertValidQuantity(item.quantity);
      const menu = await findMenu(restaurantId, item.menu_id, db);
      if (!menu) throw badRequest(`Menu ${item.menu_id} not found`);
      let unitPrice = Number(menu.price);
      for (const optionId of item.selected_options) {
        const option = await findMenuOption(restaurantId, optionId, db);
        if (!option) throw badRequest(`MenuOption ${optionId} not found`);
        unitPrice += Number(option.additional_price ?? 0);
      }
      subtotal = subtotal.plus(money(unitPrice * item.quantity));
    } else if (item.all_you_can_eat_id) {
      assertValidQuantity(item.quantity);
      const offer = await findAllYouCanEat(restaurantId, item.all_you_can_eat_id, db);
      if (!offer) throw badRequest(`AllYouCanEat offer ${item.all_you_can_eat_id} not found`);
      subtotal = subtotal.plus(money(Number(offer.price) * item.quantity));
    } else {
      throw badRequest(ITEM_REFERENCE_REQUIRED);
    }
  }
  return subtotal;
};

/* ---------- Livraison ---------- */

export interface DeliveryQuote {
  eligible: boolean;
  items_subtotal: number;
  delivery_fee: number;
  amount_total: number;
  distance_km: number | null;
  shortfall_amount: number;
  next_min_order_amount: number | null;
  message: string;
  applied_tier: { min_km: number; max_km: number; price: number; min_order_amount: number } | null;
}

const serializeTier = (tier: DeliveryTier) => ({
  min_km: tier.min_km,
  max_km: tier.max_km,
  price: Number(tier.price),
  min_order_amount: Number(tier.min_order_amount),
});

const quote = (itemsSubtotal: Decimal, fields: Partial<DeliveryQuote> & Pick<DeliveryQuote, 'eligible' | 'message'>): DeliveryQuote => ({
  items_subtotal: itemsSubtotal.toNumber(),
  delivery_fee: 0,
  amount_total: itemsSubtotal.toNumber(),
  distance_km: null,
  shortfall_amount: 0,
  next_min_order_amount: null,
  applied_tier: null,
  ...fields,
});

/** Devis de livraison : distance réelle, zone maximale, puis meilleure tranche de prix applicable. */
export const resolveDeliveryQuote = async (
  restaurant: PricingRestaurant,
  customerAddress: AddressFields,
  itemsSubtotal: Decimal,
): Promise<DeliveryQuote> => {
  if (!restaurant.address) throw badRequest('Restaurant address is not configured');

  let restaurantPoint;
  let customerPoint;
  try {
    restaurantPoint = await geocodeAddress(restaurant.address);
    customerPoint = await geocodeAddress(customerAddress);
  } catch (error) {
    // Adresse introuvable : la commande est acceptée sans frais plutôt que bloquée.
    if (error instanceof AddressNotFoundError) return quote(itemsSubtotal, { eligible: true, message: 'Adresse non verifiee, commande acceptee' });
    throw badGateway('Unable to calculate delivery distance');
  }

  const distanceKm = haversine(restaurantPoint.lat, restaurantPoint.lng, customerPoint.lat, customerPoint.lng);
  const roundedDistance = pyRound(distanceKm, 2);

  const maxKm = restaurant.config?.max_delivery_km;
  if (maxKm !== null && maxKm !== undefined && distanceKm > maxKm) {
    return quote(itemsSubtotal, { eligible: false, distance_km: roundedDistance, message: 'Adresse hors zone de livraison' });
  }

  const tiers = restaurant.delivery_tiers;
  if (!tiers.length) return quote(itemsSubtotal, { eligible: true, distance_km: roundedDistance, message: 'Livraison disponible' });

  const matchingTiers = tiers.filter((tier) => tier.min_km <= distanceKm && distanceKm <= tier.max_km);
  if (!matchingTiers.length) {
    return quote(itemsSubtotal, {
      eligible: false,
      distance_km: roundedDistance,
      message: "Aucun tarif de livraison n'est configure pour cette distance",
    });
  }

  const eligibleTiers = matchingTiers.filter((tier) => itemsSubtotal.greaterThanOrEqualTo(money(tier.min_order_amount)));
  if (!eligibleTiers.length) {
    const nextThreshold = matchingTiers.map((tier) => money(tier.min_order_amount)).reduce((a, b) => (b.lessThan(a) ? b : a));
    const shortfall = nextThreshold.minus(itemsSubtotal).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
    return quote(itemsSubtotal, {
      eligible: false,
      distance_km: roundedDistance,
      shortfall_amount: shortfall.toNumber(),
      next_min_order_amount: nextThreshold.toNumber(),
      message: `Livraison disponible a partir de ${nextThreshold.toNumber().toFixed(2)} EUR pour votre zone`,
    });
  }

  // Tranche retenue : seuil de commande le plus haut, puis prix le plus bas, puis tranche la plus étroite.
  const compareTiers = (a: DeliveryTier, b: DeliveryTier) =>
    money(a.min_order_amount).comparedTo(money(b.min_order_amount)) ||
    money(b.price).comparedTo(money(a.price)) ||
    (b.max_km - b.min_km) - (a.max_km - a.min_km);
  const selected = eligibleTiers.reduce((best, tier) => (compareTiers(tier, best) > 0 ? tier : best));
  const deliveryFee = money(selected.price);
  const amountTotal = itemsSubtotal.plus(deliveryFee).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);

  return quote(itemsSubtotal, {
    eligible: true,
    delivery_fee: deliveryFee.toNumber(),
    amount_total: amountTotal.toNumber(),
    distance_km: roundedDistance,
    message: 'Livraison disponible',
    applied_tier: serializeTier(selected),
  });
};

/* ---------- Total de la commande ---------- */

export interface OrderPricing {
  items_subtotal: Decimal;
  delivery_fee: Decimal;
  delivery_distance_km: Decimal | null;
  discount_amount: Decimal;
  discounted_subtotal: Decimal;
  amount_before_discount: Decimal;
  amount_total: Decimal;
  promo_code: string | null;
  discount_type: string | null;
  discount_value: Decimal | null;
}

/** Totaux d'une commande (calculate_order_pricing). */
export const calculateOrderPricing = async ({
  restaurant,
  orderType,
  itemsSubtotal: rawSubtotal,
  address,
  promoCode,
  db = prisma,
}: {
  restaurant: PricingRestaurant;
  orderType: string;
  itemsSubtotal: Decimal;
  address: AddressFields | null;
  promoCode?: string | null;
  db?: DbClient;
}): Promise<OrderPricing> => {
  const itemsSubtotal = money(rawSubtotal);
  let deliveryFee = new Decimal('0.00');
  let deliveryDistanceKm: Decimal | null = null;

  if (orderType === 'delivery' && address !== null) {
    const deliveryQuote = await resolveDeliveryQuote(restaurant, address, itemsSubtotal);
    if (!deliveryQuote.eligible) throw badRequest(deliveryQuote.message);
    deliveryFee = money(deliveryQuote.delivery_fee);
    deliveryDistanceKm = deliveryQuote.distance_km !== null ? money(deliveryQuote.distance_km) : null;
  }

  let discountAmount = new Decimal('0.00');
  let discountType: string | null = null;
  let discountValue: Decimal | null = null;
  let normalizedPromoCode: string | null = null;
  if (promoCode) {
    const [promo, amount] = await validatePromoCodeForOrder(restaurant.id, promoCode, itemsSubtotal, db);
    discountAmount = amount;
    discountType = promo.discount_type;
    discountValue = money(promo.discount_value);
    normalizedPromoCode = promo.code;
  }

  const discountedSubtotal = maxDecimal(ZERO, itemsSubtotal.minus(discountAmount));
  return {
    items_subtotal: itemsSubtotal,
    delivery_fee: deliveryFee,
    delivery_distance_km: deliveryDistanceKm,
    discount_amount: money(discountAmount),
    discounted_subtotal: money(discountedSubtotal),
    amount_before_discount: money(itemsSubtotal.plus(deliveryFee)),
    amount_total: money(discountedSubtotal.plus(deliveryFee)),
    promo_code: normalizedPromoCode,
    discount_type: discountType,
    discount_value: discountValue,
  };
};

type RecalculableOrder = {
  id: number;
  type: string;
  restaurant_id: number;
  promo_code: string | null;
  address: AddressFields | null;
  items: { parent_order_item_id: number | null; subtotal: Prisma.Decimal | number }[];
};

/** Totaux recalculés après un ajout ou un retrait d'article (recalculate_order_delivery_totals). */
export const recalculateOrderDeliveryTotals = async (order: RecalculableOrder, db: DbClient = prisma) => {
  const itemsSubtotal = money(
    order.items
      .filter((item) => item.parent_order_item_id === null)
      .reduce((sum, item) => sum.plus(money(item.subtotal)), new Decimal(0)),
  );

  if (order.type !== 'delivery' || order.address === null) {
    if (order.promo_code) {
      const [, discountAmount] = await validatePromoCodeForOrder(order.restaurant_id, order.promo_code, itemsSubtotal, db);
      return {
        items_subtotal: itemsSubtotal,
        delivery_fee: new Decimal('0.00'),
        delivery_distance_km: null,
        discount_amount: discountAmount,
        amount_before_discount: itemsSubtotal,
        amount_total: money(itemsSubtotal.minus(discountAmount)),
      };
    }
    return {
      items_subtotal: itemsSubtotal,
      delivery_fee: new Decimal('0.00'),
      delivery_distance_km: null,
      discount_amount: new Decimal('0.00'),
      amount_before_discount: itemsSubtotal,
      amount_total: itemsSubtotal,
    };
  }

  const restaurant = await loadPricingRestaurant(order.restaurant_id, db);
  if (!restaurant) throw notFound('Restaurant not found');
  const deliveryQuote = await resolveDeliveryQuote(restaurant, order.address, itemsSubtotal);
  if (!deliveryQuote.eligible) throw badRequest(deliveryQuote.message);

  const deliveryFee = money(deliveryQuote.delivery_fee);
  const deliveryDistanceKm = deliveryQuote.distance_km !== null ? money(deliveryQuote.distance_km) : null;
  if (order.promo_code) {
    const [, discountAmount] = await validatePromoCodeForOrder(order.restaurant_id, order.promo_code, itemsSubtotal, db);
    const discountedSubtotal = money(maxDecimal(ZERO, itemsSubtotal.minus(discountAmount)));
    return {
      items_subtotal: itemsSubtotal,
      delivery_fee: deliveryFee,
      delivery_distance_km: deliveryDistanceKm,
      discount_amount: discountAmount,
      amount_before_discount: money(itemsSubtotal.plus(deliveryFee)),
      amount_total: money(discountedSubtotal.plus(deliveryFee)),
    };
  }
  return {
    items_subtotal: itemsSubtotal,
    delivery_fee: deliveryFee,
    delivery_distance_km: deliveryDistanceKm,
    discount_amount: new Decimal('0.00'),
    amount_before_discount: money(itemsSubtotal.plus(deliveryFee)),
    amount_total: money(deliveryQuote.amount_total),
  };
};

