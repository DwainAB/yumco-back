/**
 * Restaurants (restaurant_service.py).
 */
import { prisma } from '../../db/prisma.js';
import type { Prisma } from '../../generated/prisma/client.js';
import { applySubscriptionPlan, PLAN_LIMITS, PLAN_TOKEN_LIMITS } from '../subscriptions/subscriptions.service.js';
import { restaurantInclude } from './restaurants.serializers.js';
import type { DeliveryTierCreate, OpeningHoursCreate, RestaurantConfigUpdate, RestaurantCreate, RestaurantUpdate } from './restaurants.schemas.js';

/** Valeurs par défaut de RestaurantConfig côté SQLAlchemy (la base n'en a pas). */
export const RESTAURANT_CONFIG_DEFAULTS = {
  accept_orders: false,
  preparation_time: 30,
  midday_delivery: true,
  evening_delivery: true,
  pickup: true,
  onsite: true,
  reservation: true,
  all_you_can_eat: false,
  a_la_carte: true,
  payment_online: false,
  payment_onsite: false,
  printer_enabled: false,
} as const;

/** Valeurs par défaut de Restaurant côté SQLAlchemy. */
const RESTAURANT_DEFAULTS = {
  is_deleted: false,
  stripe_charges_enabled: false,
  stripe_payouts_enabled: false,
  stripe_details_submitted: false,
  subscription_interval: 'month',
  subscription_cancel_at_period_end: false,
  has_tablet_rental: false,
  has_printer_rental: false,
} as const;

/** Champs fournis explicitement (y compris à null), comme model_dump(exclude_unset=True). */
const providedFields = <T extends object>(data: T) =>
  Object.fromEntries(Object.entries(data).filter(([, value]) => value !== undefined)) as Partial<T>;

const tierRows = (restaurantId: number, tiers: DeliveryTierCreate[]) =>
  tiers.map((tier) => ({ restaurant_id: restaurantId, min_km: tier.min_km, max_km: tier.max_km, price: tier.price, min_order_amount: tier.min_order_amount }));

const openingHoursRows = (restaurantId: number, hours: OpeningHoursCreate[]) =>
  hours.map((h) => ({
    restaurant_id: restaurantId,
    day: h.day,
    lunch_open: h.lunch_open ?? null,
    lunch_close: h.lunch_close ?? null,
    dinner_open: h.dinner_open ?? null,
    dinner_close: h.dinner_close ?? null,
    is_closed: h.is_closed,
  }));

const configData = (config: RestaurantConfigUpdate | null | undefined) => providedFields(config ?? {}) as Prisma.RestaurantConfigUncheckedUpdateInput;

export const getRestaurant = (restaurantId: number) =>
  prisma.restaurant.findFirst({ where: { id: restaurantId, is_deleted: false }, include: restaurantInclude });

export const getRestaurantsByUser = (userId: number) =>
  prisma.restaurant.findMany({
    where: { is_deleted: false, roles: { some: { user_id: userId } } },
    include: restaurantInclude,
    orderBy: { id: 'asc' },
  });

export const getAllRestaurants = (deleted: boolean) =>
  prisma.restaurant.findMany({ where: { is_deleted: deleted }, include: restaurantInclude, orderBy: { id: 'asc' } });

/** Crée le restaurant, son adresse, sa configuration, ses tranches de livraison et ses horaires en une transaction. */
export const createRestaurant = async (data: RestaurantCreate) => {
  const restaurantId = await prisma.$transaction(async (tx) => {
    const address = await tx.address.create({ data: data.address });
    const plan = data.subscription_plan || 'starter';
    const restaurant = await tx.restaurant.create({
      data: {
        ...RESTAURANT_DEFAULTS,
        name: data.name,
        email: data.email,
        phone: data.phone,
        google_review_url: data.google_review_url ?? null,
        address_id: address.id,
        subscription_plan: plan,
        ai_monthly_quota: PLAN_LIMITS[plan],
        ai_usage_count: 0,
        ai_monthly_token_quota: PLAN_TOKEN_LIMITS[plan],
        ai_token_usage_count: 0,
      },
    });
    await tx.restaurantConfig.create({
      data: { ...RESTAURANT_CONFIG_DEFAULTS, ...configData(data.config), restaurant_id: restaurant.id } as Prisma.RestaurantConfigUncheckedCreateInput,
    });
    if (data.delivery_tiers?.length) await tx.deliveryTier.createMany({ data: tierRows(restaurant.id, data.delivery_tiers) });
    if (data.opening_hours?.length) await tx.openingHours.createMany({ data: openingHoursRows(restaurant.id, data.opening_hours) });
    return restaurant.id;
  });
  return prisma.restaurant.findUniqueOrThrow({ where: { id: restaurantId }, include: restaurantInclude });
};

/** Suppression « douce » : le restaurant est seulement marqué comme supprimé. */
export const softDeleteRestaurant = (restaurantId: number) =>
  prisma.restaurant.update({ where: { id: restaurantId }, data: { is_deleted: true } });

const NESTED_FIELDS = new Set(['address', 'config', 'delivery_tiers', 'opening_hours', 'subscription_plan']);

export const updateRestaurant = async (restaurantId: number, addressId: number | null, data: RestaurantUpdate) => {
  const updated = await prisma.$transaction(async (tx) => {
    if (data.address) {
      if (addressId !== null) {
        const address = await tx.address.findUnique({ where: { id: addressId } });
        if (address) await tx.address.update({ where: { id: addressId }, data: providedFields(data.address) as Prisma.AddressUpdateInput });
      }
    }

    if (data.config) {
      const existing = await tx.restaurantConfig.findUnique({ where: { restaurant_id: restaurantId } });
      if (existing) await tx.restaurantConfig.update({ where: { id: existing.id }, data: configData(data.config) });
      else {
        await tx.restaurantConfig.create({
          data: { ...RESTAURANT_CONFIG_DEFAULTS, ...configData(data.config), restaurant_id: restaurantId } as Prisma.RestaurantConfigUncheckedCreateInput,
        });
      }
    }

    if (data.delivery_tiers != null) {
      await tx.deliveryTier.deleteMany({ where: { restaurant_id: restaurantId } });
      if (data.delivery_tiers.length) await tx.deliveryTier.createMany({ data: tierRows(restaurantId, data.delivery_tiers) });
    }

    if (data.opening_hours != null) {
      await tx.openingHours.deleteMany({ where: { restaurant_id: restaurantId } });
      if (data.opening_hours.length) await tx.openingHours.createMany({ data: openingHoursRows(restaurantId, data.opening_hours) });
    }

    const scalars = Object.fromEntries(Object.entries(providedFields(data)).filter(([field]) => !NESTED_FIELDS.has(field)));
    return tx.restaurant.update({ where: { id: restaurantId }, data: scalars as Prisma.RestaurantUncheckedUpdateInput });
  });

  if (data.subscription_plan !== undefined) {
    await applySubscriptionPlan(updated, data.subscription_plan as string, data.ai_cycle_started_at);
  }
  return prisma.restaurant.findUniqueOrThrow({ where: { id: restaurantId }, include: restaurantInclude });
};
