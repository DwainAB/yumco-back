/**
 * Réponses restaurants (RestaurantResponse et ses sous-objets).
 */
import type { Address, DeliveryTier, OpeningHours, Prisma, RestaurantConfig } from '../../generated/prisma/client.js';
import { datetime, datetimeOrNull, decimalString } from '../../lib/serialize.js';

/** Relations chargées pour construire un RestaurantResponse. */
export const restaurantInclude = {
  address: true,
  config: true,
  delivery_tiers: { orderBy: { id: 'asc' } },
  opening_hours: { orderBy: { id: 'asc' } },
} as const satisfies Prisma.RestaurantInclude;

export type RestaurantWithRelations = Prisma.RestaurantGetPayload<{ include: typeof restaurantInclude }>;

export const toAddressResponse = (address: Address) => ({
  id: address.id,
  street: address.street,
  city: address.city,
  postal_code: address.postal_code,
  country: address.country,
  created_at: datetime(address.created_at!),
});

export const toRestaurantConfigResponse = (config: RestaurantConfig) => ({
  id: config.id,
  restaurant_id: config.restaurant_id,
  accept_orders: config.accept_orders,
  preparation_time: config.preparation_time,
  midday_delivery: config.midday_delivery,
  evening_delivery: config.evening_delivery,
  pickup: config.pickup,
  onsite: config.onsite,
  reservation: config.reservation,
  all_you_can_eat: config.all_you_can_eat,
  a_la_carte: config.a_la_carte,
  payment_online: config.payment_online,
  payment_onsite: config.payment_onsite,
  max_delivery_km: config.max_delivery_km,
  printer_enabled: config.printer_enabled,
  printer_name: config.printer_name,
  printer_host: config.printer_host,
  printer_port: config.printer_port,
  printer_paper_width: config.printer_paper_width,
});

export const toDeliveryTierResponse = (tier: DeliveryTier) => ({
  id: tier.id,
  min_km: tier.min_km,
  max_km: tier.max_km,
  price: decimalString(tier.price),
  min_order_amount: decimalString(tier.min_order_amount),
});

export const toOpeningHoursResponse = (hours: OpeningHours) => ({
  id: hours.id,
  day: hours.day,
  lunch_open: hours.lunch_open,
  lunch_close: hours.lunch_close,
  dinner_open: hours.dinner_open,
  dinner_close: hours.dinner_close,
  is_closed: hours.is_closed ?? false,
});

export const toRestaurantResponse = (restaurant: RestaurantWithRelations) => ({
  id: restaurant.id,
  name: restaurant.name,
  email: restaurant.email,
  phone: restaurant.phone,
  google_review_url: restaurant.google_review_url,
  timezone: restaurant.timezone,
  address: restaurant.address ? toAddressResponse(restaurant.address) : null,
  stripe_id: restaurant.stripe_id,
  stripe_charges_enabled: restaurant.stripe_charges_enabled,
  stripe_payouts_enabled: restaurant.stripe_payouts_enabled,
  stripe_details_submitted: restaurant.stripe_details_submitted,
  subscription_plan: restaurant.subscription_plan,
  subscription_interval: restaurant.subscription_interval,
  subscription_status: restaurant.subscription_status,
  subscription_cancel_at_period_end: restaurant.subscription_cancel_at_period_end,
  subscription_current_period_ends_at: datetimeOrNull(restaurant.subscription_current_period_ends_at),
  stripe_customer_id: restaurant.stripe_customer_id,
  stripe_subscription_id: restaurant.stripe_subscription_id,
  has_tablet_rental: restaurant.has_tablet_rental,
  has_printer_rental: restaurant.has_printer_rental,
  ai_monthly_quota: restaurant.ai_monthly_quota,
  ai_usage_count: restaurant.ai_usage_count,
  ai_monthly_token_quota: restaurant.ai_monthly_token_quota,
  ai_token_usage_count: restaurant.ai_token_usage_count,
  ai_cycle_started_at: datetimeOrNull(restaurant.ai_cycle_started_at),
  created_at: datetime(restaurant.created_at!),
  config: restaurant.config ? toRestaurantConfigResponse(restaurant.config) : null,
  delivery_tiers: restaurant.delivery_tiers.map(toDeliveryTierResponse),
  opening_hours: restaurant.opening_hours.map(toOpeningHoursResponse),
});
