/**
 * Validation des entrées restaurants (schemas/restaurant.py, restaurant_config.py, address.py,
 * delivery_tiers.py, opening_hours.py).
 */
import { Prisma } from '../../generated/prisma/client.js';
import { ge, MODEL_VALIDATOR, py, valueError, z } from '../../lib/validation.js';

export const ALLOWED_SUBSCRIPTION_PLANS = ['starter', 'pro_ai', 'business_ai'] as const;
const SORTED_PLANS = [...ALLOWED_SUBSCRIPTION_PLANS].sort().join(', ');

export const AddressCreate = z.object({
  street: py.str(),
  city: py.str(),
  postal_code: py.str(),
  country: py.str(),
});
export type AddressCreate = z.output<typeof AddressCreate>;

export const AddressUpdate = z.object({
  street: py.str().nullable().optional(),
  city: py.str().nullable().optional(),
  postal_code: py.str().nullable().optional(),
  country: py.str().nullable().optional(),
});

export const RestaurantConfigUpdate = z.object({
  accept_orders: py.bool().nullable().optional(),
  preparation_time: py.int().nullable().optional(),
  midday_delivery: py.bool().nullable().optional(),
  evening_delivery: py.bool().nullable().optional(),
  pickup: py.bool().nullable().optional(),
  onsite: py.bool().nullable().optional(),
  reservation: py.bool().nullable().optional(),
  all_you_can_eat: py.bool().nullable().optional(),
  a_la_carte: py.bool().nullable().optional(),
  payment_online: py.bool().nullable().optional(),
  payment_onsite: py.bool().nullable().optional(),
  max_delivery_km: py.int().nullable().optional(),
  printer_enabled: py.bool().nullable().optional(),
  printer_name: py.str().nullable().optional(),
  printer_host: py.str().nullable().optional(),
  printer_port: py
    .int()
    .superRefine((value, ctx) => {
      if (value <= 0 || value > 65535) valueError(ctx, 'printer_port must be between 1 and 65535', [], value);
    })
    .nullable()
    .optional(),
  printer_paper_width: py
    .int()
    .superRefine((value, ctx) => {
      if (value !== 58 && value !== 80) valueError(ctx, 'printer_paper_width must be 58 or 80', [], value);
    })
    .nullable()
    .optional(),
});
export type RestaurantConfigUpdate = z.output<typeof RestaurantConfigUpdate>;

export const DeliveryTierCreate = z
  .object({
    min_km: py.int().superRefine(ge(0)),
    max_km: py.int().superRefine(ge(0)),
    price: py.decimal().superRefine(ge(0)),
    min_order_amount: py.decimal().superRefine(ge(0)).default(() => new Prisma.Decimal(0)),
  })
  .superRefine((tier, ctx) => {
    if (tier.max_km < tier.min_km) valueError(ctx, 'max_km must be greater than or equal to min_km');
  }, MODEL_VALIDATOR);
export type DeliveryTierCreate = z.output<typeof DeliveryTierCreate>;

export const OpeningHoursCreate = z.object({
  day: py.int(),
  lunch_open: py.str().nullable().optional(),
  lunch_close: py.str().nullable().optional(),
  dinner_open: py.str().nullable().optional(),
  dinner_close: py.str().nullable().optional(),
  is_closed: py.bool().default(false),
});
export type OpeningHoursCreate = z.output<typeof OpeningHoursCreate>;

const subscriptionPlan = () =>
  py.str().transform((value, ctx) => {
    const normalized = value.trim().toLowerCase();
    if (!(ALLOWED_SUBSCRIPTION_PLANS as readonly string[]).includes(normalized)) {
      valueError(ctx, `subscription_plan must be one of: ${SORTED_PLANS}`, [], value);
      return z.NEVER;
    }
    return normalized;
  });

/** Les tranches ne doivent ni se chevaucher ni partager une borne (des tranches identiques peuvent s'empiler). */
const deliveryTiers = () =>
  z.array(DeliveryTierCreate).superRefine((tiers, ctx) => {
    const unique = [...new Map(tiers.map((t) => [`${t.min_km}:${t.max_km}`, [t.min_km, t.max_km] as const])).values()].sort(
      (a, b) => a[0] - b[0] || a[1] - b[1],
    );
    for (let index = 0; index < unique.length - 1; index += 1) {
      if (unique[index + 1][0] <= unique[index][1]) {
        valueError(ctx, 'delivery_tiers ranges must not overlap or share a boundary; use identical ranges only when stacking pricing rules');
        return;
      }
    }
  }, MODEL_VALIDATOR);

/** URL d'avis Google : vide → null, sinon http(s) obligatoire. */
const googleReviewUrl = () =>
  py
    .str()
    .transform((value, ctx) => {
      const normalized = value.trim();
      if (!normalized) return null;
      if (!normalized.startsWith('http://') && !normalized.startsWith('https://')) {
        valueError(ctx, 'google_review_url must start with http:// or https://', [], value);
        return z.NEVER;
      }
      return normalized;
    })
    .nullable()
    .optional();

export const RestaurantCreate = z.object({
  name: py.str(),
  email: py.email(),
  phone: py.str(),
  google_review_url: googleReviewUrl(),
  address: AddressCreate,
  subscription_plan: subscriptionPlan().default('starter'),
  config: RestaurantConfigUpdate.nullable().optional(),
  delivery_tiers: deliveryTiers().nullable().optional(),
  opening_hours: z.array(OpeningHoursCreate).nullable().optional(),
});
export type RestaurantCreate = z.output<typeof RestaurantCreate>;

export const RestaurantUpdate = z.object({
  name: py.str().nullable().optional(),
  email: py.email().nullable().optional(),
  phone: py.str().nullable().optional(),
  google_review_url: googleReviewUrl(),
  stripe_id: py.str().nullable().optional(),
  timezone: py.str().nullable().optional(),
  subscription_plan: subscriptionPlan().nullable().optional(),
  subscription_status: py.str().nullable().optional(),
  ai_monthly_quota: py.int().nullable().optional(),
  ai_usage_count: py.int().nullable().optional(),
  ai_monthly_token_quota: py.int().nullable().optional(),
  ai_token_usage_count: py.int().nullable().optional(),
  ai_cycle_started_at: py.datetime().nullable().optional(),
  address: AddressUpdate.nullable().optional(),
  config: RestaurantConfigUpdate.nullable().optional(),
  delivery_tiers: deliveryTiers().nullable().optional(),
  opening_hours: z.array(OpeningHoursCreate).nullable().optional(),
});
export type RestaurantUpdate = z.output<typeof RestaurantUpdate>;
