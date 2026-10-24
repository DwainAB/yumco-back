/**
 * Commandes (routes/order.py).
 */
import { Router, type Response } from 'express';
import { DateTime } from 'luxon';
import { prisma } from '../../db/prisma.js';
import { addBackgroundTask } from '../../lib/background.js';
import { badRequest, notFound } from '../../lib/http-error.js';
import { logger } from '../../lib/logger.js';
import { zoneOf } from '../../lib/time.js';
import { ge, intParams, le, matches, py, validateRequest, z } from '../../lib/validation.js';
import { authenticate, currentUser, restaurantMember } from '../../middleware/auth.js';
import { getOrderAnalytics } from '../analytics/order-analytics.service.js';
import { syncOrderItemsToHubrise, syncOrderStatusToHubrise, syncOrderToHubrise } from '../hubrise/hubrise.service.js';
import { notifyNewOrder } from '../notifications/push.service.js';
import { scheduleReviewFollowup } from '../review-followups/review-followups.service.js';
import { ExportPeriodError, generateOrdersCsv, generateOrdersSummaryPdf, getExportOrders } from './exports.service.js';
import {
  loadEmailOrder,
  sendOrderCancelled,
  sendOrderCompleted,
  sendOrderConfirmed,
  sendOrderPreparing,
  sendOrderReceipt,
} from './order-emails.service.js';
import { DeliveryQuoteRequest, OrderCreate, OrderItemList, OrderReceiptEmailRequest, OrderStatusUpdate, OrderUpdate } from './orders.schemas.js';
import { toOrderResponse } from './orders.serializers.js';
import { addOrderItems, createOrder, findOrderOr404, removeOrderItem } from './orders.service.js';
import { loadPricingRestaurant, resolveDeliveryQuote } from './pricing.service.js';
import { generateReceipt, receiptInclude } from './receipts.service.js';
import { getOrderSlots } from './slots.service.js';

export const ordersRouter = Router();

const restaurantParams = intParams('restaurant_id');
const orderParams = intParams('restaurant_id', 'order_id');

/** E-mail de suivi envoyé après la réponse, avec la commande relue en base. */
const queueStatusEmail = (res: Response, orderId: number, restaurantId: number, status: string, preparationTime?: number | null) => {
  const senders = { preparing: 'send_order_preparing', completed: 'send_order_completed', cancelled: 'send_order_cancelled' } as const;
  if (!(status in senders)) return;
  addBackgroundTask(res, senders[status as keyof typeof senders], async () => {
    const [order, restaurant] = await Promise.all([
      loadEmailOrder(orderId),
      prisma.restaurant.findUnique({ where: { id: restaurantId }, include: { config: true } }),
    ]);
    if (!order || !restaurant) return;
    if (status === 'preparing') await sendOrderPreparing(order, restaurant, preparationTime);
    else if (status === 'completed') await sendOrderCompleted(order, restaurant);
    else await sendOrderCancelled(order, restaurant);
  });
};

/** Après un changement de statut : e-mail au client, demande d'avis programmée, statut envoyé à HubRise. */
const afterStatusChange = async (res: Response, orderId: number, restaurantId: number, status: string, preparationTime?: number | null) => {
  const order = await prisma.order.findUniqueOrThrow({ where: { id: orderId }, include: { customer: true } });
  if (status === 'completed') {
    const restaurant = await prisma.restaurant.findUnique({ where: { id: restaurantId } });
    if (restaurant) await scheduleReviewFollowup(order, restaurant);
  }
  queueStatusEmail(res, orderId, restaurantId, status, preparationTime);
  if (order.hubrise_order_id) addBackgroundTask(res, 'sync_order_status_to_hubrise', () => syncOrderStatusToHubrise(orderId, status));
};

const freeTable = async (tableId: number | null) => {
  if (!tableId) return;
  const table = await prisma.table.findUnique({ where: { id: tableId } });
  if (table) await prisma.table.update({ where: { id: table.id }, data: { is_available: true } });
};

ordersRouter.post('/restaurants/:restaurant_id/delivery/quote', async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: DeliveryQuoteRequest });
  const restaurant = await loadPricingRestaurant(params.restaurant_id);
  if (!restaurant) throw notFound('Restaurant not found');
  res.json(await resolveDeliveryQuote(restaurant, body.address, body.items_subtotal));
});

ordersRouter.get('/restaurants/:restaurant_id/orders/slots', async (req, res) => {
  const { params, query } = validateRequest(req, {
    params: restaurantParams,
    query: z.object({ type: py.str(), date: py.date().optional() }),
  });
  if (query.type !== 'pickup' && query.type !== 'delivery') throw badRequest("type must be 'pickup' or 'delivery'");
  const restaurant = await prisma.restaurant.findUnique({ where: { id: params.restaurant_id } });
  if (!restaurant) throw notFound('Restaurant not found');
  const isoDate = query.date ? query.date.toISOString().slice(0, 10) : null;
  res.json(await getOrderSlots(restaurant, query.type, isoDate));
});

ordersRouter.post('/restaurants/:restaurant_id/orders', async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: OrderCreate });
  const restaurantId = params.restaurant_id;
  const config = await prisma.restaurantConfig.findUnique({ where: { restaurant_id: restaurantId } });
  if (config?.payment_online && !config.payment_onsite) throw badRequest('Online payment is required for this restaurant');

  let order = await createOrder(restaurantId, body);
  if (order.is_draft) {
    res.status(201).json(toOrderResponse(order));
    return;
  }

  let hubriseConnected = false;
  if (order.type === 'pickup' || order.type === 'delivery') {
    const connection = await prisma.hubriseConnection.findUnique({ where: { restaurant_id: restaurantId } });
    if (connection) {
      hubriseConnected = true;
      await prisma.order.update({ where: { id: order.id }, data: { hubrise_sync_status: 'pending', hubrise_last_error: null } });
      order = await findOrderOr404(restaurantId, order.id);
      logger.info({ order_id: order.id, restaurant_id: restaurantId, location_id: connection.hubrise_location_id }, '[hubrise] scheduling order sync');
    }
  }

  const orderId = order.id;
  const orderNumber = order.order_number;
  addBackgroundTask(res, 'send_order_confirmed', async () => {
    const [emailOrder, restaurant] = await Promise.all([loadEmailOrder(orderId), prisma.restaurant.findUnique({ where: { id: restaurantId } })]);
    if (emailOrder && restaurant) await sendOrderConfirmed(emailOrder, restaurant);
  });
  addBackgroundTask(res, 'notify_new_order', () => notifyNewOrder(restaurantId, orderNumber));
  if (hubriseConnected) addBackgroundTask(res, 'sync_order_to_hubrise', () => syncOrderToHubrise(orderId));
  res.status(201).json(toOrderResponse(order));
});

/** Envoie en cuisine une commande sur place préparée en brouillon. */
ordersRouter.post('/restaurants/:restaurant_id/orders/:order_id/submit', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: orderParams });
  const order = await prisma.order.findFirst({ where: { id: params.order_id, restaurant_id: params.restaurant_id } });
  if (!order) throw notFound('Order not found');
  if (order.type !== 'onsite') throw badRequest('Only onsite orders can be submitted');
  if (!order.is_draft) throw badRequest('Order is already submitted');

  let submitted = await prisma.order.update({ where: { id: order.id }, data: { is_draft: false } });
  const connection = await prisma.hubriseConnection.findUnique({ where: { restaurant_id: params.restaurant_id } });
  if (connection) {
    submitted = await prisma.order.update({ where: { id: order.id }, data: { hubrise_sync_status: 'pending', hubrise_last_error: null } });
    logger.info({ order_id: order.id, restaurant_id: params.restaurant_id, location_id: connection.hubrise_location_id }, '[hubrise] scheduling onsite order sync');
    addBackgroundTask(res, 'sync_order_to_hubrise', () => syncOrderToHubrise(order.id));
  }
  addBackgroundTask(res, 'notify_new_order', () => notifyNewOrder(params.restaurant_id, submitted.order_number));
  res.json({ id: submitted.id, status: submitted.status, is_draft: submitted.is_draft });
});

const ListOrdersQuery = z.object({
  table_id: py.int().optional(),
  status: py.str().optional(),
  date_from: py.date().optional(),
  date_to: py.date().optional(),
  month: py.int().superRefine(ge(1)).superRefine(le(12)).optional(),
  year: py.int().superRefine(ge(2000)).superRefine(le(2100)).optional(),
});

ordersRouter.get('/restaurants/:restaurant_id/orders', ...restaurantMember, async (req, res) => {
  const { params, query } = validateRequest(req, { params: restaurantParams, query: ListOrdersQuery });
  const restaurant = await prisma.restaurant.findUnique({ where: { id: params.restaurant_id } });
  if (!restaurant) throw notFound('Restaurant not found');

  const { date_from: dateFrom, date_to: dateTo, month, year } = query;
  if (dateFrom && dateTo && dateFrom > dateTo) throw badRequest('date_from must be before or equal to date_to');
  if ((dateFrom === undefined) !== (dateTo === undefined)) throw badRequest('date_from and date_to must be provided together');
  if ((dateFrom || dateTo) && (month !== undefined || year !== undefined)) throw badRequest('date range filters cannot be combined with month/year');
  if (month !== undefined && year === undefined) throw badRequest('year is required when month is provided');
  if (month === undefined && year !== undefined) throw badRequest('month is required when year is provided');

  let createdAt: { gte: Date; lt: Date } | undefined;
  if (dateFrom && dateTo) {
    // Jours entiers à l'heure du restaurant.
    const zone = zoneOf(restaurant.timezone);
    const day = (value: Date) => DateTime.fromISO(value.toISOString().slice(0, 10), { zone }).startOf('day');
    createdAt = { gte: day(dateFrom).toJSDate(), lt: day(dateTo).plus({ days: 1 }).toJSDate() };
  } else if (month !== undefined && year !== undefined) {
    // extract(month/year) sur created_at : mois calendaire en UTC (fuseau de la base).
    createdAt = { gte: new Date(Date.UTC(year, month - 1, 1)), lt: new Date(Date.UTC(year, month, 1)) };
  }

  const orders = await prisma.order.findMany({
    where: {
      restaurant_id: params.restaurant_id,
      ...(query.table_id !== undefined ? { table_id: query.table_id } : {}),
      ...(query.status !== undefined ? { status: query.status } : {}),
      ...(createdAt ? { created_at: createdAt } : {}),
    },
    include: { items: { orderBy: { id: 'asc' } }, customer: true, address: true, prepared_by_user: true },
    orderBy: [{ created_at: 'desc' }, { id: 'desc' }],
  });
  res.json(orders.map(toOrderResponse));
});

ordersRouter.get('/restaurants/:restaurant_id/orders/analytics', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  const analytics = await getOrderAnalytics(params.restaurant_id);
  if (!analytics) throw notFound('Restaurant not found');
  res.json(analytics);
});

const exportFormat = py.str().superRefine(matches('^(csv|pdf)$'));

ordersRouter.get('/restaurants/:restaurant_id/orders/export', ...restaurantMember, async (req, res) => {
  const { params, query } = validateRequest(req, {
    params: restaurantParams,
    query: ListOrdersQuery.pick({ date_from: true, date_to: true, month: true, year: true }).extend({ format: exportFormat.default('csv') }),
  });
  const isoDay = (value?: Date) => (value ? value.toISOString().slice(0, 10) : null);
  let exportData;
  try {
    exportData = await getExportOrders(params.restaurant_id, {
      startDate: isoDay(query.date_from),
      endDate: isoDay(query.date_to),
      month: query.month ?? null,
      year: query.year ?? null,
    });
  } catch (error) {
    if (error instanceof ExportPeriodError) throw badRequest(error.message);
    throw error;
  }
  if (!exportData) throw notFound('Restaurant not found');

  const { restaurant, orders, zone, periodLabel } = exportData;
  const safePeriod = periodLabel.replaceAll('/', '-').replaceAll(' ', '_');
  const safeName = restaurant.name.toLowerCase().replaceAll(' ', '_');
  const [payload, extension, mediaType] =
    query.format === 'pdf'
      ? [await generateOrdersSummaryPdf(restaurant, orders, zone, periodLabel), 'pdf', 'application/pdf']
      : [generateOrdersCsv(restaurant, orders, zone, periodLabel), 'csv', 'text/csv; charset=utf-8'];
  res
    .set({ 'Content-Type': mediaType, 'Content-Disposition': `attachment; filename="recap_commandes_${safeName}_${safePeriod}.${extension}"` })
    .send(payload);
});

ordersRouter.get('/restaurants/:restaurant_id/orders/:order_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: orderParams });
  res.json(toOrderResponse(await findOrderOr404(params.restaurant_id, params.order_id)));
});

ordersRouter.put('/restaurants/:restaurant_id/orders/:order_id', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: orderParams, body: OrderUpdate });
  const order = await prisma.order.findFirst({ where: { id: params.order_id, restaurant_id: params.restaurant_id } });
  if (!order) throw notFound('Order not found');

  const changes: Record<string, unknown> = Object.fromEntries(Object.entries(body).filter(([, value]) => value !== undefined));
  const newStatus = body.status;
  if (order.is_draft && newStatus != null) throw badRequest('Draft onsite orders must be submitted before changing status');
  if (newStatus === 'preparing' && !('preparing_by' in changes)) changes.preparing_by = currentUser(req).id;
  if (newStatus === 'completed' && !order.completed_at) changes.completed_at = new Date();
  if ((newStatus === 'completed' || newStatus === 'cancelled') && order.table_id) await freeTable(order.table_id);

  await prisma.order.update({ where: { id: order.id }, data: changes });
  if (newStatus) await afterStatusChange(res, order.id, params.restaurant_id, newStatus);
  res.json(toOrderResponse(await findOrderOr404(params.restaurant_id, order.id)));
});

ordersRouter.get('/restaurants/:restaurant_id/orders/:order_id/receipt', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: orderParams });
  const order = await prisma.order.findFirst({ where: { id: params.order_id, restaurant_id: params.restaurant_id }, include: receiptInclude });
  if (!order) throw notFound('Order not found');
  const restaurant = await prisma.restaurant.findUniqueOrThrow({ where: { id: params.restaurant_id } });
  const pdf = await generateReceipt(order, restaurant);
  res
    .set({ 'Content-Type': 'application/pdf', 'Content-Disposition': `inline; filename=ticket_${order.order_number.replaceAll('#', '')}.pdf` })
    .send(pdf);
});

ordersRouter.post('/restaurants/:restaurant_id/orders/:order_id/receipt/send', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: orderParams, body: OrderReceiptEmailRequest });
  const order = await prisma.order.findFirst({ where: { id: params.order_id, restaurant_id: params.restaurant_id }, include: receiptInclude });
  if (!order) throw notFound('Order not found');
  const restaurant = await prisma.restaurant.findUnique({ where: { id: params.restaurant_id } });
  if (!restaurant) throw notFound('Restaurant not found');

  const targetEmail = body.email || order.customer?.email;
  if (!targetEmail) throw badRequest('No customer email available for this order');
  addBackgroundTask(res, 'send_order_receipt', () => sendOrderReceipt(order, restaurant, targetEmail));
  res.json({ message: 'Receipt email queued successfully', email: targetEmail });
});

ordersRouter.post('/restaurants/:restaurant_id/orders/:order_id/status', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: orderParams, body: OrderStatusUpdate });
  const order = await prisma.order.findFirst({ where: { id: params.order_id, restaurant_id: params.restaurant_id } });
  if (!order) throw notFound('Order not found');
  const connection = await prisma.hubriseConnection.findUnique({ where: { restaurant_id: params.restaurant_id } });
  if (order.is_draft && connection) throw badRequest('Draft onsite orders must be submitted before changing status');

  // Sans HubRise, une commande sur place en brouillon peut passer directement à un autre statut.
  const changes: Record<string, unknown> = { status: body.status, ...(order.is_draft ? { is_draft: false } : {}) };
  if (body.status === 'preparing') changes.preparing_by = body.preparing_by || currentUser(req).id;
  else if (body.status === 'completed') changes.completed_at = new Date();
  if ((body.status === 'completed' || body.status === 'cancelled') && order.table_id) await freeTable(order.table_id);

  await prisma.order.update({ where: { id: order.id }, data: changes });
  await afterStatusChange(res, order.id, params.restaurant_id, body.status, body.preparation_time);
  res.json(toOrderResponse(await findOrderOr404(params.restaurant_id, order.id)));
});

ordersRouter.post('/restaurants/:restaurant_id/orders/:order_id/items', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: orderParams, body: OrderItemList });
  const order = await addOrderItems(params.restaurant_id, params.order_id, body);
  if (order.type === 'onsite' && order.hubrise_order_id) addBackgroundTask(res, 'sync_order_items_to_hubrise', () => syncOrderItemsToHubrise(order.id));
  res.json(toOrderResponse(order));
});

ordersRouter.delete('/restaurants/:restaurant_id/orders/:order_id/items/:item_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: intParams('restaurant_id', 'order_id', 'item_id') });
  const order = await removeOrderItem(params.restaurant_id, params.order_id, params.item_id);
  if (order.type === 'onsite' && order.hubrise_order_id) addBackgroundTask(res, 'sync_order_items_to_hubrise', () => syncOrderItemsToHubrise(order.id));
  res.json(toOrderResponse(order));
});

ordersRouter.delete('/restaurants/:restaurant_id/orders/:order_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: orderParams });
  const order = await prisma.order.findFirst({ where: { id: params.order_id, restaurant_id: params.restaurant_id } });
  if (!order) throw notFound('Order not found');
  if (order.type === 'onsite' && !order.is_draft) throw badRequest('Submitted onsite orders must be cancelled instead of deleted');
  await freeTable(order.table_id);
  await prisma.order.delete({ where: { id: order.id } });
  res.status(204).end();
});
