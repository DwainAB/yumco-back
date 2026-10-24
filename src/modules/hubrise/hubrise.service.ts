/**
 * Intégration HubRise (hubrise_service.py) : connexion OAuth, envoi des commandes à la caisse,
 * synchronisation des statuts dans les deux sens et commandes de test.
 */
import { createHmac, timingSafeEqual } from 'node:crypto';
import { env } from '../../config/env.js';
import { prisma } from '../../db/prisma.js';
import type { HubriseConnection, Prisma } from '../../generated/prisma/client.js';
import { badGateway, badRequest, HttpError, notFound } from '../../lib/http-error.js';
import { logger } from '../../lib/logger.js';
import { buildHubriseOrderPatchPayload, buildHubriseOrderPayload, hubriseMoney, serviceType, type HubriseItem } from './hubrise-payloads.js';

const HUBRISE_TOKEN_URL = 'https://manager.hubrise.com/oauth2/v1/token';
const HUBRISE_API_BASE_URL = 'https://api.hubrise.com/v1';
const TIMEOUT_MS = 20_000;

const truncate = (text: string) => text.slice(0, 255);

const syncInclude = { customer: true, address: true, items: { orderBy: { id: 'asc' } } } as const satisfies Prisma.OrderInclude;

/* ---------- Connexion OAuth ---------- */

/** Identifiant du restaurant transmis dans `state` : un entier, ou du JSON {"restaurant_id": …}. */
export const parseRestaurantIdFromState = (state: string | undefined): number => {
  if (!state) throw badRequest('Missing state');
  if (/^\s*[-+]?\d+\s*$/.test(state)) return Number.parseInt(state, 10);
  let payload: unknown;
  try {
    payload = JSON.parse(state);
  } catch {
    throw badRequest('Invalid state');
  }
  const restaurantId = (payload as { restaurant_id?: unknown } | null)?.restaurant_id;
  if (typeof restaurantId !== 'number' || !Number.isInteger(restaurantId)) throw badRequest('Invalid state');
  return restaurantId;
};

export interface HubriseTokens {
  access_token: string;
  location_id: string;
  account_id?: string;
  refresh_token?: string;
  token_type?: string;
  scope?: string;
}

export const exchangeCodeForTokens = async (code: string): Promise<HubriseTokens> => {
  if (!env.HUBRISE_CLIENT_ID || !env.HUBRISE_CLIENT_SECRET) throw new HttpError(500, 'HubRise OAuth is not configured');
  const response = await fetch(HUBRISE_TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      grant_type: 'authorization_code',
      code,
      redirect_uri: env.HUBRISE_REDIRECT_URI,
      client_id: env.HUBRISE_CLIENT_ID,
      client_secret: env.HUBRISE_CLIENT_SECRET,
    }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (response.status >= 400) throw badGateway(`HubRise token exchange failed (${response.status})`);
  const data = (await response.json()) as Partial<HubriseTokens>;
  if (!data.access_token || !data.location_id) throw badGateway('HubRise response is missing required fields');
  return data as HubriseTokens;
};

export const saveHubriseConnection = async (restaurantId: number, tokens: HubriseTokens) => {
  const restaurant = await prisma.restaurant.findFirst({ where: { id: restaurantId, is_deleted: false } });
  if (!restaurant) throw notFound('Restaurant not found');
  const fields = {
    hubrise_location_id: tokens.location_id,
    hubrise_account_id: tokens.account_id || tokens.location_id,
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token ?? null,
    token_type: tokens.token_type || 'Bearer',
    scope: tokens.scope || '',
  };
  return prisma.hubriseConnection.upsert({
    where: { restaurant_id: restaurantId },
    create: { restaurant_id: restaurantId, ...fields },
    update: { ...fields, updated_at: new Date() },
  });
};

/** Demande à HubRise de prévenir Yumco des changements de statut des commandes. */
export const registerHubriseOrderCallback = async (connection: HubriseConnection) => {
  if (!env.HUBRISE_WEBHOOK_URL) {
    logger.info({ reason: 'missing_webhook_url', restaurant_id: connection.restaurant_id }, '[hubrise] callback registration skipped');
    return null;
  }
  const response = await fetch(`${HUBRISE_API_BASE_URL}/callback`, {
    method: 'POST',
    headers: { 'X-Access-Token': connection.access_token, 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: env.HUBRISE_WEBHOOK_URL, events: { order: ['update'] } }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  const text = await response.text();
  const data = text ? (JSON.parse(text) as unknown) : {};
  logger.info({ restaurant_id: connection.restaurant_id, status_code: response.status, response: data }, '[hubrise] callback registration');
  if (response.status >= 400) throw badGateway(`HubRise callback registration failed (${response.status})`);
  return data;
};

/* ---------- Webhook (HubRise → Yumco) ---------- */

export const verifyHubriseSignature = (rawBody: Buffer, signature: string | undefined) => {
  if (!signature || !env.HUBRISE_CLIENT_SECRET) return false;
  const expected = createHmac('sha256', env.HUBRISE_CLIENT_SECRET).update(rawBody).digest('hex');
  return expected.length === signature.length && timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
};

export const mapHubriseStatusToYumco = (status: string | null | undefined, orderType?: string | null) => {
  if (status === 'new' || status === 'received') return 'pending';
  const inProgress = ['accepted', 'in_preparation', 'awaiting_collection', 'in_delivery'];
  if (orderType === 'onsite' && status && inProgress.includes(status)) return 'pending';
  if (status && inProgress.includes(status)) return 'preparing';
  if (status === 'completed') return 'completed';
  if (status === 'cancelled' || status === 'rejected' || status === 'delivery_failed') return 'cancelled';
  return null;
};

type HubriseEvent = {
  resource_type?: string;
  event_type?: string;
  order_id?: string;
  new_state?: { id?: string; status?: string; private_ref?: unknown };
};

/** Applique un changement de statut venu de la caisse. Renvoie la commande et ses statuts avant / après. */
export const applyHubriseOrderUpdate = async (event: HubriseEvent) => {
  if (event.resource_type !== 'order' || event.event_type !== 'update') return null;
  const newState = event.new_state ?? {};
  const hubriseOrderId = newState.id || event.order_id;
  if (!hubriseOrderId) {
    logger.info({ reason: 'missing_order_id', payload: event }, '[hubrise] order update ignored');
    return null;
  }

  let order = await prisma.order.findFirst({ where: { hubrise_order_id: hubriseOrderId } });
  if (!order) {
    const privateRef = newState.private_ref;
    if (privateRef !== undefined && privateRef !== null && /^\d+$/.test(String(privateRef))) {
      order = await prisma.order.findUnique({ where: { id: Number(privateRef) } });
    }
  }
  if (!order) {
    logger.info({ reason: 'order_not_found', hubrise_order_id: hubriseOrderId }, '[hubrise] order update ignored');
    return null;
  }

  const hubriseStatus = newState.status ?? null;
  const yumcoStatus = mapHubriseStatusToYumco(hubriseStatus, order.type);
  const previousStatus = order.status;
  const changes: Prisma.OrderUpdateInput = {
    hubrise_order_id: hubriseOrderId,
    hubrise_raw_status: hubriseStatus,
    hubrise_sync_status: 'sent',
    hubrise_last_error: null,
    hubrise_synced_at: new Date(),
  };
  if (yumcoStatus) {
    changes.status = yumcoStatus;
    if (yumcoStatus === 'completed' && !order.completed_at) changes.completed_at = new Date();
    if ((yumcoStatus === 'completed' || yumcoStatus === 'cancelled') && order.table_id) {
      const table = await prisma.table.findUnique({ where: { id: order.table_id } });
      if (table) await prisma.table.update({ where: { id: table.id }, data: { is_available: true } });
    }
  }
  const updated = await prisma.order.update({ where: { id: order.id }, data: changes });
  logger.info(
    { order_id: updated.id, hubrise_order_id: hubriseOrderId, hubrise_status: hubriseStatus, yumco_status: updated.status },
    '[hubrise] order status synced',
  );
  return { order: updated, previousStatus, currentStatus: updated.status };
};

/* ---------- Envoi des commandes (Yumco → HubRise) ---------- */

/** Réponse HubRise : JSON, {} si vide, ou le texte brut s'il n'est pas lisible. */
const readResponse = async (response: Response) => {
  const text = await response.text();
  if (!text) return { text, data: {} as Record<string, unknown> };
  try {
    return { text, data: JSON.parse(text) as Record<string, unknown> };
  } catch {
    return { text, data: { raw_response: text } as Record<string, unknown> };
  }
};

const hubriseRequest = (connection: HubriseConnection, method: string, path: string, body?: unknown) =>
  fetch(`${HUBRISE_API_BASE_URL}${path}`, {
    method,
    headers: { 'X-Access-Token': connection.access_token, ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });

const postHubriseOrder = async (connection: HubriseConnection, payload: unknown) => {
  const response = await hubriseRequest(connection, 'POST', '/location/orders', payload);
  const { text, data } = await readResponse(response);
  return { status: response.status, data, text };
};

export const mapYumcoStatusToHubrise = (status: string | null | undefined) =>
  status === 'preparing' ? 'accepted' : status === 'completed' ? 'completed' : status === 'cancelled' ? 'cancelled' : null;

const tableNumberOf = async (tableId: number | null) => {
  if (!tableId) return null;
  const table = await prisma.table.findUnique({ where: { id: tableId } });
  return table?.table_number ?? null;
};

const markSyncFailure = (errorMessage: string) => ({
  hubrise_sync_status: 'failed',
  hubrise_last_error: truncate(errorMessage),
  hubrise_synced_at: null,
});

/** Envoie une nouvelle commande à la caisse et garde une trace de l'échange (sync_order_to_hubrise). */
export const syncOrderToHubrise = async (orderId: number) => {
  logger.info({ order_id: orderId }, '[hubrise] sync started');
  const order = await prisma.order.findUnique({ where: { id: orderId }, include: syncInclude });
  if (!order || !['pickup', 'delivery', 'onsite'].includes(order.type)) {
    logger.info({ order_id: orderId, reason: 'order_missing_or_unsupported_type' }, '[hubrise] sync skipped');
    return;
  }
  const connection = await prisma.hubriseConnection.findUnique({ where: { restaurant_id: order.restaurant_id } });
  if (!connection) {
    logger.info({ order_id: orderId, reason: 'no_connection' }, '[hubrise] sync skipped');
    return;
  }

  const payload = buildHubriseOrderPayload(order, await tableNumberOf(order.table_id));
  const log = await prisma.$transaction(async (tx) => {
    const created = await tx.hubriseOrderLog.create({
      data: {
        order_id: order.id,
        restaurant_id: order.restaurant_id,
        hubrise_location_id: connection.hubrise_location_id,
        request_payload: payload as unknown as Prisma.InputJsonValue,
        status: 'pending',
      },
    });
    await tx.order.update({ where: { id: order.id }, data: { hubrise_sync_status: 'pending', hubrise_last_error: null } });
    return created;
  });
  logger.info({ order_id: orderId, location_id: connection.hubrise_location_id, payload }, '[hubrise] sending order');

  let result;
  try {
    result = await postHubriseOrder(connection, payload);
  } catch (error) {
    const errorMessage = `HubRise request error: ${(error as Error).message}`;
    await prisma.order.update({ where: { id: order.id }, data: markSyncFailure(errorMessage) });
    await prisma.hubriseOrderLog.update({ where: { id: log.id }, data: { status: 'failed', error_message: errorMessage } });
    logger.warn({ order_id: orderId, error: String(error) }, '[hubrise] order sync failed');
    return;
  }
  logger.info({ order_id: orderId, status_code: result.status, response: result.data }, '[hubrise] response received');

  const responsePayload = result.data as Prisma.InputJsonValue;
  if (result.status >= 200 && result.status < 300) {
    await prisma.order.update({
      where: { id: order.id },
      data: {
        hubrise_order_id: (result.data.id as string | undefined) ?? null,
        hubrise_sync_status: 'sent',
        hubrise_last_error: null,
        hubrise_synced_at: new Date(),
      },
    });
    await prisma.hubriseOrderLog.update({ where: { id: log.id }, data: { response_payload: responsePayload, status: 'sent' } });
  } else {
    // (En Python, ce cas plantait quand HubRise répondait sans message.)
    const errorMessage = (result.data.message as string | undefined) || result.text || 'HubRise request failed';
    await prisma.order.update({ where: { id: order.id }, data: markSyncFailure(errorMessage) });
    await prisma.hubriseOrderLog.update({
      where: { id: log.id },
      data: { response_payload: responsePayload, status: 'failed', error_message: errorMessage },
    });
  }
};

/** Envoie le nouveau statut d'une commande à la caisse (sync_order_status_to_hubrise). */
export const syncOrderStatusToHubrise = async (orderId: number, yumcoStatus: string) => {
  const hubriseStatus = mapYumcoStatusToHubrise(yumcoStatus);
  if (!hubriseStatus) return;
  const order = await prisma.order.findUnique({ where: { id: orderId } });
  if (!order?.hubrise_order_id) {
    logger.info({ order_id: orderId, reason: 'missing_order_or_hubrise_id' }, '[hubrise] status sync skipped');
    return;
  }
  const connection = await prisma.hubriseConnection.findUnique({ where: { restaurant_id: order.restaurant_id } });
  if (!connection) {
    logger.info({ order_id: orderId, reason: 'no_connection' }, '[hubrise] status sync skipped');
    return;
  }
  logger.info(
    { order_id: orderId, hubrise_order_id: order.hubrise_order_id, yumco_status: yumcoStatus, hubrise_status: hubriseStatus },
    '[hubrise] sending order status',
  );

  let response: Response;
  try {
    response = await hubriseRequest(connection, 'PATCH', `/location/orders/${order.hubrise_order_id}`, { status: hubriseStatus });
  } catch (error) {
    await prisma.order.update({ where: { id: orderId }, data: { hubrise_last_error: truncate(`HubRise status sync error: ${(error as Error).message}`) } });
    logger.warn({ order_id: orderId, error: String(error) }, '[hubrise] status sync failed');
    return;
  }
  const { text, data } = await readResponse(response);
  logger.info({ order_id: orderId, status_code: response.status, response: data }, '[hubrise] status response received');

  if (response.ok) {
    await prisma.order.update({
      where: { id: orderId },
      data: { hubrise_raw_status: (data.status as string | undefined) ?? hubriseStatus, hubrise_sync_status: 'sent', hubrise_last_error: null, hubrise_synced_at: new Date() },
    });
  } else {
    await prisma.order.update({ where: { id: orderId }, data: { hubrise_last_error: truncate((data.message as string | undefined) || text || 'HubRise status sync failed') } });
  }
};

/** Remplace les articles d'une commande sur place déjà envoyée (sync_order_items_to_hubrise). */
export const syncOrderItemsToHubrise = async (orderId: number) => {
  const order = await prisma.order.findUnique({ where: { id: orderId }, include: syncInclude });
  if (!order?.hubrise_order_id) {
    logger.info({ order_id: orderId, reason: 'missing_order_or_hubrise_id' }, '[hubrise] order patch skipped');
    return;
  }
  const connection = await prisma.hubriseConnection.findUnique({ where: { restaurant_id: order.restaurant_id } });
  if (!connection) {
    logger.info({ order_id: orderId, reason: 'no_connection' }, '[hubrise] order patch skipped');
    return;
  }

  const currentResponse = await hubriseRequest(connection, 'GET', `/location/orders/${order.hubrise_order_id}`);
  const current = await readResponse(currentResponse);
  if (!currentResponse.ok) {
    await prisma.order.update({
      where: { id: orderId },
      data: { hubrise_sync_status: 'failed', hubrise_last_error: truncate((current.data.message as string | undefined) || current.text || 'HubRise order fetch failed') },
    });
    logger.info({ order_id: orderId, reason: 'fetch_failed', status_code: currentResponse.status, response: current.data }, '[hubrise] order patch skipped');
    return;
  }

  const payload = buildHubriseOrderPatchPayload(order, await tableNumberOf(order.table_id));
  const existingItems = (current.data.items as { id?: string; deleted?: boolean }[] | undefined) ?? [];
  const deleteOps = existingItems.filter((item) => item.id && !item.deleted).map((item) => ({ id: item.id, deleted: true }));
  payload.items = [...deleteOps, ...payload.items];
  logger.info({ order_id: orderId, hubrise_order_id: order.hubrise_order_id, payload }, '[hubrise] sending order patch');

  let response: Response;
  try {
    response = await hubriseRequest(connection, 'PATCH', `/location/orders/${order.hubrise_order_id}`, payload);
  } catch (error) {
    await prisma.order.update({
      where: { id: orderId },
      data: { hubrise_sync_status: 'failed', hubrise_last_error: truncate(`HubRise order patch error: ${(error as Error).message}`) },
    });
    logger.warn({ order_id: orderId, error: String(error) }, '[hubrise] order patch failed');
    return;
  }
  const { text, data } = await readResponse(response);
  logger.info({ order_id: orderId, status_code: response.status, response: data }, '[hubrise] patch response received');

  await prisma.order.update({
    where: { id: orderId },
    data: response.ok
      ? { hubrise_sync_status: 'sent', hubrise_last_error: null, hubrise_synced_at: new Date() }
      : { hubrise_sync_status: 'failed', hubrise_last_error: truncate((data.message as string | undefined) || text || 'HubRise order patch failed') },
  });
};

/* ---------- Commandes de test (admin) ---------- */

export interface HubriseTestOrderRequest {
  order_type: 'pickup' | 'delivery';
  is_paid: boolean;
  item_kind: 'product' | 'menu';
  quantity: number;
  include_paid_option: boolean;
  include_free_option: boolean;
}

const testCustomer = (orderType: string) => ({
  first_name: 'Jean',
  last_name: 'Dupont',
  phone: '0601020304',
  ...(orderType === 'delivery' ? { address_1: '10 Rue de la Paix', postal_code: '75002', city: 'Paris', country: 'FR' } : {}),
});

const buildTestOrderPayload = async (restaurantId: number, data: HubriseTestOrderRequest) => {
  const connection = await prisma.hubriseConnection.findUnique({ where: { restaurant_id: restaurantId } });
  if (!connection) throw notFound('HubRise connection not found for this restaurant');

  const quantity = Math.max(1, data.quantity);
  const items: HubriseItem[] = [];
  let totalAmount: number;

  if (data.item_kind === 'product') {
    const product = await prisma.product.findFirst({
      where: { restaurant_id: restaurantId, is_deleted: false, is_available: true, available_online: true },
      orderBy: { id: 'asc' },
    });
    if (!product) throw badRequest('No available online product found for this restaurant');
    const unitPrice = Number(product.price);
    totalAmount = unitPrice * quantity;
    items.push({ private_ref: `test-product-${product.id}`, product_name: product.name, price: hubriseMoney(unitPrice), quantity: String(quantity) });
  } else {
    const menu = await prisma.menu.findFirst({
      where: { restaurant_id: restaurantId, is_available: true, available_online: true },
      include: { categories: { orderBy: { id: 'asc' }, include: { options: { orderBy: { id: 'asc' } } } } },
      orderBy: { id: 'asc' },
    });
    if (!menu) throw badRequest('No available online menu found for this restaurant');

    const options = menu.categories.flatMap((category) => category.options);
    const selected: NonNullable<HubriseItem['options']> = [];
    if (data.include_paid_option) {
      const paid = options.find((option) => Number(option.additional_price ?? 0) > 0);
      if (paid) selected.push({ option_list_name: 'Customization', name: paid.name, price: hubriseMoney(Number(paid.additional_price)), quantity: 1 });
    }
    if (data.include_free_option) {
      const free = options.find((option) => Number(option.additional_price ?? 0) === 0);
      if (free && !selected.some((option) => option.name === free.name)) {
        selected.push({ option_list_name: 'Customization', name: free.name, price: hubriseMoney(Number(free.additional_price ?? 0)), quantity: 1 });
      }
    }
    const item: HubriseItem = { private_ref: `test-menu-${menu.id}`, product_name: menu.name, price: hubriseMoney(Number(menu.price)), quantity: String(quantity) };
    if (selected.length) item.options = selected;
    items.push(item);
    totalAmount = Number(menu.price) * quantity + selected.reduce((sum, option) => sum + Number(option.price.split(' ')[0]) * quantity, 0);
  }

  const suffix = Math.floor(Date.now() / 1000);
  let sellerNotes = 'Commande de test HubRise envoyee par Yumco.';
  sellerNotes += data.order_type === 'delivery' ? ' Livraison de test.' : ' Retrait sur place de test.';
  const payload: Record<string, unknown> = {
    channel: 'yumco-test',
    ref: `TEST-${restaurantId}-${suffix}`,
    private_ref: `test-${restaurantId}-${data.item_kind}-${data.order_type}-${suffix}`,
    status: 'new',
    service_type: serviceType(data.order_type),
    asap: true,
    items,
    seller_notes: sellerNotes,
    customer: testCustomer(data.order_type),
  };
  if (data.is_paid) {
    payload.payments = [{ name: 'Yumco', ref: 'YUMCO-TEST', amount: hubriseMoney(totalAmount), info: { payment_status: 'paid', test: true } }];
    payload.seller_notes = `${sellerNotes} Commande deja payee.`;
  } else {
    payload.seller_notes = `${sellerNotes} Paiement a encaisser sur place.`;
  }
  return { connection, payload };
};

export const sendHubriseTestOrder = async (restaurantId: number, data: HubriseTestOrderRequest) => {
  const { connection, payload } = await buildTestOrderPayload(restaurantId, data);
  const result = await postHubriseOrder(connection, payload);
  logger.info({ restaurant_id: restaurantId, status_code: result.status, payload, response: result.data }, '[hubrise] test order response');
  if (result.status < 200 || result.status >= 300) {
    throw badGateway({ message: 'HubRise test order failed', status_code: result.status, response: result.data });
  }
  return { payload, response: result.data };
};
