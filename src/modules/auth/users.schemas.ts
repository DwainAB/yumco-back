/**
 * Validation des entrées utilisateurs (schemas/user.py).
 */
import { MODEL_VALIDATOR, py, valueError, z } from '../../lib/validation.js';

export const UserCreate = z
  .object({
    email: py.email(),
    first_name: py.str(),
    last_name: py.str(),
    phone: py.str().nullable().optional(),
    restaurant_id: py.int().nullable().optional(),
    role: py.str().nullable().optional(),
    is_admin: py.bool().default(false),
  })
  .superRefine((data, ctx) => {
    const restaurantId = data.restaurant_id ?? null;
    const role = data.role ?? null;
    if ((restaurantId === null) !== (role === null)) valueError(ctx, 'restaurant_id and role must be provided together');
    else if (data.is_admin && restaurantId !== null) valueError(ctx, 'admin users cannot be attached to a restaurant at creation');
    else if (!data.is_admin && restaurantId === null) valueError(ctx, 'non-admin users must be attached to a restaurant');
  }, MODEL_VALIDATOR);
export type UserCreate = z.output<typeof UserCreate>;

export const UserLogin = z.object({ email: py.email(), password: py.str() });

export const UserUpdate = z.object({
  first_name: py.str().nullable().optional(),
  last_name: py.str().nullable().optional(),
  phone: py.str().nullable().optional(),
  expo_push_token: py.str().nullable().optional(),
  notify_orders: py.bool().nullable().optional(),
  notify_reservations: py.bool().nullable().optional(),
  email: py.email().nullable().optional(),
  password: py.str().nullable().optional(),
  role: py.str().nullable().optional(),
});
export type UserUpdate = z.output<typeof UserUpdate>;

export const UserDeviceRegisterRequest = z.object({
  expo_push_token: py.str(),
  platform: py.str().nullable().optional(),
  device_name: py.str().nullable().optional(),
});

export const UserDeviceUnregisterRequest = z.object({ expo_push_token: py.str() });

export const ResetPasswordQuery = z.object({ email: py.email() });
