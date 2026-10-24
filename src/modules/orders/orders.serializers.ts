/**
 * Réponses commandes (OrderResponse, OrderItemResponse).
 */
import type { OrderItem, Prisma } from '../../generated/prisma/client.js';
import { datetime, datetimeOrNull, float, floatOrNull } from '../../lib/serialize.js';
import { toUserBrief } from '../auth/users.serializers.js';
import { toCustomerResponse } from '../customers/customers.routes.js';
import { toAddressResponse } from '../restaurants/restaurants.serializers.js';

export const orderInclude = {
  items: { orderBy: { id: 'asc' } },
  customer: true,
  address: true,
  prepared_by_user: true,
} as const satisfies Prisma.OrderInclude;

export type OrderWithRelations = Prisma.OrderGetPayload<{ include: typeof orderInclude }>;

export const toOrderItemResponse = (item: OrderItem) => ({
  id: item.id,
  order_id: item.order_id,
  name: item.name,
  quantity: item.quantity,
  unit_price: float(item.unit_price),
  subtotal: float(item.subtotal),
  comment: item.comment,
  product_id: item.product_id,
  menu_id: item.menu_id,
  menu_option_id: item.menu_option_id,
  all_you_can_eat_id: item.all_you_can_eat_id,
  parent_order_item_id: item.parent_order_item_id,
  created_at: datetime(item.created_at!),
});

export const toOrderResponse = (order: OrderWithRelations) => ({
  id: order.id,
  order_number: order.order_number,
  restaurant_id: order.restaurant_id,
  customer_id: order.customer_id,
  type: order.type,
  status: order.status,
  is_draft: order.is_draft,
  hubrise_raw_status: order.hubrise_raw_status,
  payment_status: order.payment_status,
  items_subtotal: float(order.items_subtotal),
  delivery_fee: float(order.delivery_fee),
  delivery_distance_km: floatOrNull(order.delivery_distance_km),
  promo_code: order.promo_code,
  discount_type: order.discount_type,
  discount_value: floatOrNull(order.discount_value),
  discount_amount: float(order.discount_amount),
  amount_before_discount: float(order.amount_before_discount),
  amount_total: float(order.amount_total),
  comment: order.comment,
  requested_time: datetimeOrNull(order.requested_time),
  completed_at: datetimeOrNull(order.completed_at),
  address_id: order.address_id,
  table_id: order.table_id,
  preparing_by: order.preparing_by,
  prepared_by_user: order.prepared_by_user ? toUserBrief(order.prepared_by_user) : null,
  customer: order.customer ? toCustomerResponse(order.customer) : null,
  address: order.address ? toAddressResponse(order.address) : null,
  items: order.items.map(toOrderItemResponse),
  created_at: datetime(order.created_at!),
});
