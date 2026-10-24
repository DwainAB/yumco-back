/**
 * Validation des codes promo (schemas/promo_code.py).
 */
import { Prisma } from '../../generated/prisma/client.js';
import { MODEL_VALIDATOR, py, valueError, z } from '../../lib/validation.js';
import { AddressCreate } from '../restaurants/restaurants.schemas.js';
import { OrderItemCreate } from '../orders/orders.schemas.js';

const code = (field: string) =>
  py.str().transform((value, ctx) => {
    const normalized = value.trim().toUpperCase();
    if (!normalized) {
      valueError(ctx, `${field} is required`, [], value);
      return z.NEVER;
    }
    return normalized;
  });

const discountType = () =>
  py.str().transform((value, ctx) => {
    const normalized = value.trim().toLowerCase();
    if (normalized !== 'percent' && normalized !== 'fixed') {
      valueError(ctx, "discount_type must be 'percent' or 'fixed'", [], value);
      return z.NEVER;
    }
    return normalized;
  });

const positiveDecimal = (field: string) =>
  py.decimal().superRefine((value, ctx) => {
    if (value.lessThanOrEqualTo(0)) valueError(ctx, `${field} must be greater than 0`, [], value.toString());
  });

const nonNegativeDecimal = (field: string) =>
  py.decimal().superRefine((value, ctx) => {
    if (value.lessThan(0)) valueError(ctx, `${field} must be greater than or equal to 0`, [], value.toString());
  });

const usageLimit = () =>
  py.int().superRefine((value, ctx) => {
    if (value <= 0) valueError(ctx, 'usage_limit must be greater than 0', [], value);
  });

/** Une date vide ("") vaut null. */
const optionalDatetime = () => z.preprocess((value) => (typeof value === 'string' && !value.trim() ? null : value), py.datetime().nullable().optional());

const checkDates = (data: { start_at?: Date | null; end_at?: Date | null }, ctx: z.core.$RefinementCtx) => {
  if (data.end_at && data.start_at && data.end_at.getTime() <= data.start_at.getTime()) valueError(ctx, 'end_at must be after start_at');
};

export const PromoCodeCreate = z
  .object({
    code: code('code'),
    discount_type: discountType(),
    discount_value: positiveDecimal('discount_value'),
    minimum_order_amount: nonNegativeDecimal('minimum_order_amount').nullable().optional(),
    usage_limit: usageLimit().nullable().optional(),
    start_at: optionalDatetime(),
    end_at: optionalDatetime(),
    is_active: py.bool().default(true),
  })
  .superRefine(checkDates, MODEL_VALIDATOR);
export type PromoCodeCreate = z.output<typeof PromoCodeCreate>;

export const PromoCodeUpdate = z
  .object({
    code: code('code').nullable().optional(),
    discount_type: discountType().nullable().optional(),
    discount_value: positiveDecimal('discount_value').nullable().optional(),
    minimum_order_amount: nonNegativeDecimal('minimum_order_amount').nullable().optional(),
    usage_limit: usageLimit().nullable().optional(),
    start_at: optionalDatetime(),
    end_at: optionalDatetime(),
    is_active: py.bool().nullable().optional(),
  })
  .superRefine(checkDates, MODEL_VALIDATOR);
export type PromoCodeUpdate = z.output<typeof PromoCodeUpdate>;

export const PromoCodeValidationRequest = z.object({
  promo_code: code('promo_code'),
  type: py.str(),
  items: z.array(OrderItemCreate),
  address: AddressCreate.nullable().optional(),
});

export type DecimalValue = Prisma.Decimal;
