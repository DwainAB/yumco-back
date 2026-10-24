/**
 * Administration Yumco (routes/admin.py).
 */
import { Router } from 'express';
import { env } from '../../config/env.js';
import { prisma } from '../../db/prisma.js';
import { addBackgroundTask } from '../../lib/background.js';
import { badRequest, notFound } from '../../lib/http-error.js';
import { datetime, datetimeOrNull } from '../../lib/serialize.js';
import { intParams, py, validateRequest, z } from '../../lib/validation.js';
import { authenticate, requireAdmin } from '../../middleware/auth.js';
import { toUserResponse } from '../auth/users.serializers.js';
import { getUserById } from '../auth/users.service.js';
import { hubriseStatus } from '../hubrise/hubrise.routes.js';
import { sendHubriseTestOrder, syncOrderItemsToHubrise, syncOrderToHubrise } from '../hubrise/hubrise.service.js';
import { toRestaurantResponse } from '../restaurants/restaurants.serializers.js';
import { getAllRestaurants } from '../restaurants/restaurants.service.js';

const HubriseTestOrderRequest = z.object({
  order_type: py.literal('pickup', 'delivery'),
  is_paid: py.bool().default(false),
  item_kind: py.literal('product', 'menu').default('product'),
  quantity: py.int().default(1),
  include_paid_option: py.bool().default(true),
  include_free_option: py.bool().default(true),
});

export const adminRouter = Router();

const admin = [authenticate, requireAdmin];
const restaurantParams = intParams('restaurant_id');
const orderParams = intParams('restaurant_id', 'order_id');

const findRestaurant = async (restaurantId: number) => {
  const restaurant = await prisma.restaurant.findUnique({ where: { id: restaurantId } });
  if (!restaurant) throw notFound('Restaurant not found');
  return restaurant;
};

const findRestaurantOrder = async (restaurantId: number, orderId: number) => {
  const order = await prisma.order.findFirst({ where: { id: orderId, restaurant_id: restaurantId } });
  if (!order) throw notFound('Order not found');
  return order;
};

const requireConnection = async (restaurantId: number) => {
  const connection = await prisma.hubriseConnection.findUnique({ where: { restaurant_id: restaurantId } });
  if (!connection) throw notFound('HubRise connection not found for this restaurant');
  return connection;
};

adminRouter.get('/admin/users', ...admin, async (_req, res) => {
  const users = await prisma.user.findMany({ include: { roles: { orderBy: { id: 'asc' } } }, orderBy: { id: 'asc' } });
  res.json(users.map(toUserResponse));
});

/** En Python, cette route ne vérifiait pas le rôle admin (correction de sécurité). */
adminRouter.get('/admin/users/:user_id', ...(env.STRICT_RESTAURANT_ACCESS ? admin : [authenticate]), async (req, res) => {
  const { params } = validateRequest(req, { params: intParams('user_id') });
  const user = await getUserById(params.user_id);
  if (!user) throw notFound('User not found');
  res.json(toUserResponse(user));
});

adminRouter.get('/admin/restaurants', ...admin, async (_req, res) => {
  res.json((await getAllRestaurants(false)).map(toRestaurantResponse));
});

adminRouter.get('/admin/restaurants/deleted', ...admin, async (_req, res) => {
  res.json((await getAllRestaurants(true)).map(toRestaurantResponse));
});

/** Suppression définitive : toutes les données du restaurant partent avec lui (cascades de la base). */
adminRouter.delete('/admin/restaurants/:restaurant_id', ...admin, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  await findRestaurant(params.restaurant_id);
  await prisma.restaurant.deleteMany({ where: { id: params.restaurant_id } });
  res.status(204).end();
});

adminRouter.get('/admin/restaurants/:restaurant_id/hubrise/status', ...admin, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  await findRestaurant(params.restaurant_id);
  res.json(await hubriseStatus(params.restaurant_id));
});

adminRouter.post('/admin/restaurants/:restaurant_id/hubrise/test-order', ...admin, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: HubriseTestOrderRequest });
  await findRestaurant(params.restaurant_id);
  const { payload, response } = await sendHubriseTestOrder(params.restaurant_id, body);
  const connection = await requireConnection(params.restaurant_id);
  res.json({
    connected: true,
    restaurant_id: params.restaurant_id,
    hubrise_location_id: connection.hubrise_location_id,
    payload,
    response,
    sent_at: datetime(new Date()),
  });
});

adminRouter.post('/admin/restaurants/:restaurant_id/hubrise/retry/orders/:order_id', ...admin, async (req, res) => {
  const { params } = validateRequest(req, { params: orderParams });
  await findRestaurant(params.restaurant_id);
  await requireConnection(params.restaurant_id);
  const order = await findRestaurantOrder(params.restaurant_id, params.order_id);
  if (!['pickup', 'delivery', 'onsite'].includes(order.type)) throw badRequest('This order type cannot be retried on HubRise');

  await prisma.order.update({ where: { id: order.id }, data: { hubrise_sync_status: 'pending', hubrise_last_error: null } });
  const patch = Boolean(order.hubrise_order_id);
  addBackgroundTask(res, patch ? 'sync_order_items_to_hubrise' : 'sync_order_to_hubrise', () =>
    patch ? syncOrderItemsToHubrise(order.id) : syncOrderToHubrise(order.id),
  );
  res.json({
    restaurant_id: params.restaurant_id,
    order_id: order.id,
    hubrise_sync_status: 'pending',
    message: patch ? 'HubRise order patch retry scheduled' : 'HubRise order sync retry scheduled',
  });
});

adminRouter.get('/admin/restaurants/:restaurant_id/hubrise/orders/:order_id', ...admin, async (req, res) => {
  const { params } = validateRequest(req, { params: orderParams });
  await findRestaurant(params.restaurant_id);
  const order = await findRestaurantOrder(params.restaurant_id, params.order_id);
  const latestLog = await prisma.hubriseOrderLog.findFirst({ where: { order_id: order.id }, orderBy: [{ created_at: 'desc' }, { id: 'desc' }] });
  res.json({
    restaurant_id: params.restaurant_id,
    order_id: order.id,
    order_type: order.type,
    order_status: order.status,
    is_draft: order.is_draft,
    hubrise_order_id: order.hubrise_order_id,
    hubrise_raw_status: order.hubrise_raw_status,
    hubrise_sync_status: order.hubrise_sync_status,
    hubrise_last_error: order.hubrise_last_error,
    hubrise_synced_at: datetimeOrNull(order.hubrise_synced_at),
    latest_log: latestLog
      ? {
          id: latestLog.id,
          status: latestLog.status,
          hubrise_location_id: latestLog.hubrise_location_id,
          request_payload: latestLog.request_payload,
          response_payload: latestLog.response_payload,
          error_message: latestLog.error_message,
          created_at: datetime(latestLog.created_at),
          updated_at: datetime(latestLog.updated_at),
        }
      : null,
  });
});
