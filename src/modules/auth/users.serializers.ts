/**
 * Réponses utilisateurs (UserResponse, UserBrief, UserDeviceResponse).
 */
import type { Role, User, UserDevice } from '../../generated/prisma/client.js';
import { datetime } from '../../lib/serialize.js';

export const toRoleInfo = (role: Pick<Role, 'restaurant_id' | 'type'>) => ({ restaurant_id: role.restaurant_id, type: role.type });

export const toUserResponse = (user: User & { roles: Role[] }) => ({
  id: user.id,
  email: user.email,
  first_name: user.first_name,
  last_name: user.last_name,
  phone: user.phone,
  created_at: datetime(user.created_at!),
  expo_push_token: user.expo_push_token,
  notify_orders: user.notify_orders,
  notify_reservations: user.notify_reservations,
  is_admin: user.is_admin ?? false,
  roles: user.roles.map(toRoleInfo),
});

export const toUserBrief = (user: Pick<User, 'id' | 'first_name' | 'last_name' | 'phone'>) => ({
  id: user.id,
  first_name: user.first_name,
  last_name: user.last_name,
  phone: user.phone,
});

export const toUserDeviceResponse = (device: UserDevice) => ({
  id: device.id,
  expo_push_token: device.expo_push_token,
  platform: device.platform,
  device_name: device.device_name,
  is_active: device.is_active,
  last_seen_at: datetime(device.last_seen_at),
});
