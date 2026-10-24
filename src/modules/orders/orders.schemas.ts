/**
 * Validation des commandes (schemas/order.py).
 */
import { ge, py, z } from '../../lib/validation.js';
import { CustomerCreate } from '../customers/customers.routes.js';
import { AddressCreate } from '../restaurants/restaurants.schemas.js';

export const OrderItemCreate = z.object({
  product_id: py.int().nullable().optional(),
  menu_id: py.int().nullable().optional(),
  all_you_can_eat_id: py.int().nullable().optional(),
  quantity: py.int().default(1),
  comment: py.str().nullable().optional(),
  /** Options choisies (identifiants de menu_options), seulement pour un menu. */
  selected_options: z.array(py.int()).default([]),
});
export type OrderItemCreate = z.output<typeof OrderItemCreate>;

export const OrderCreate = z.object({
  /** delivery | pickup | onsite */
  type: py.str(),
  promo_code: py.str().nullable().optional(),
  comment: py.str().nullable().optional(),
  requested_time: py.datetime().nullable().optional(),
  table_id: py.int().nullable().optional(),
  /** Obligatoire pour une livraison. */
  address: AddressCreate.nullable().optional(),
  /** Obligatoire sauf sur place. */
  customer: CustomerCreate.nullable().optional(),
  items: z.array(OrderItemCreate),
});
export type OrderCreate = z.output<typeof OrderCreate>;

export const OrderItemList = z.array(OrderItemCreate);

export const DeliveryQuoteRequest = z.object({
  address: AddressCreate,
  items_subtotal: py.decimal().superRefine(ge(0)),
});

export const OrderStatusUpdate = z.object({
  /** preparing | completed | cancelled */
  status: py.str(),
  preparing_by: py.int().nullable().optional(),
  /** En minutes, seulement pour l'e-mail. */
  preparation_time: py.int().nullable().optional(),
});

export const OrderReceiptEmailRequest = z.object({ email: py.email().nullable().optional() });

export const OrderUpdate = z.object({
  status: py.str().nullable().optional(),
  payment_status: py.str().nullable().optional(),
  comment: py.str().nullable().optional(),
  requested_time: py.datetime().nullable().optional(),
  preparing_by: py.int().nullable().optional(),
});

/**
 * Écriture JSON d'une commande, identique à OrderCreate.model_dump_json() de Python
 * (pending_online_orders.payload_json est lu par les deux backends pendant la bascule).
 */
export const serializeOrderCreate = (data: OrderCreate) =>
  JSON.stringify({
    type: data.type,
    promo_code: data.promo_code ?? null,
    comment: data.comment ?? null,
    requested_time: data.requested_time ? data.requested_time.toISOString().replace('.000Z', 'Z') : null,
    table_id: data.table_id ?? null,
    address: data.address ?? null,
    customer: data.customer
      ? { first_name: data.customer.first_name, last_name: data.customer.last_name, email: data.customer.email ?? null, phone: data.customer.phone ?? null }
      : null,
    items: data.items.map((item) => ({
      product_id: item.product_id ?? null,
      menu_id: item.menu_id ?? null,
      all_you_can_eat_id: item.all_you_can_eat_id ?? null,
      quantity: item.quantity,
      comment: item.comment ?? null,
      selected_options: item.selected_options,
    })),
  });
