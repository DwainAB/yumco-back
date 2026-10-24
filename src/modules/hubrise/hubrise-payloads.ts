/**
 * Commandes au format HubRise (build_hubrise_order_payload et build_hubrise_order_patch_payload).
 */
import type { Customer, Address, OrderItem } from '../../generated/prisma/client.js';

/** « 12.50 EUR » */
export const hubriseMoney = (amount: number) => `${amount.toFixed(2)} EUR`;

export const serviceType = (orderType: string) => (orderType === 'pickup' ? 'collection' : orderType === 'delivery' ? 'delivery' : 'eat_in');

/** isoformat() Python d'une date en UTC : 2026-10-24T10:00:00+00:00. */
export const pyIsoUtc = (value: Date) => {
  const iso = value.toISOString();
  const ms = value.getUTCMilliseconds();
  return `${iso.slice(0, 19)}${ms ? `.${String(ms).padStart(3, '0')}000` : ''}+00:00`;
};

export interface HubriseOrder {
  id: number;
  order_number: string;
  type: string;
  payment_status: string | null;
  amount_total: unknown;
  comment: string | null;
  requested_time: Date | null;
  items: OrderItem[];
  customer: Customer | null;
  address: Address | null;
}

export interface HubriseItem {
  private_ref?: string;
  product_name: string;
  price: string;
  quantity: string;
  customer_notes?: string;
  options?: { option_list_name: string; name: string; price: string; quantity: number }[];
}

export interface HubriseOrderPayload {
  channel: string;
  ref: string;
  private_ref: string;
  status: string;
  service_type: string;
  asap: boolean;
  items: HubriseItem[];
  seller_notes: string;
  customer_notes?: string;
  expected_time?: string;
  expected_time_pickup?: boolean;
  customer?: Record<string, string>;
  payments?: { name: string; ref: string; amount: string; info: Record<string, unknown> }[];
}

export const buildHubriseOrderPayload = (order: HubriseOrder, tableNumber: string | null): HubriseOrderPayload => {
  const childrenByParent = new Map<number, OrderItem[]>();
  for (const item of order.items) {
    if (item.parent_order_item_id === null) continue;
    childrenByParent.set(item.parent_order_item_id, [...(childrenByParent.get(item.parent_order_item_id) ?? []), item]);
  }

  const items: HubriseItem[] = order.items
    .filter((item) => item.parent_order_item_id === null)
    .map((item) => {
      const options = (childrenByParent.get(item.id) ?? []).map((child) => ({
        option_list_name: 'Customization',
        name: child.name,
        price: hubriseMoney(Number(child.unit_price)),
        quantity: child.quantity,
      }));
      const payload: HubriseItem = {
        private_ref: String(item.id),
        product_name: item.name,
        price: hubriseMoney(Number(item.unit_price)),
        quantity: String(item.quantity),
      };
      if (item.comment) payload.customer_notes = item.comment;
      if (options.length) payload.options = options;
      return payload;
    });

  let customer: Record<string, string> | null = null;
  if (order.type === 'onsite' && tableNumber) {
    customer = { first_name: 'Table', last_name: String(tableNumber) };
  } else if (order.customer) {
    customer = { first_name: order.customer.first_name, last_name: order.customer.last_name };
    if (order.customer.email) customer.email = order.customer.email;
    if (order.customer.phone) customer.phone = order.customer.phone;
    if (order.address) {
      customer.address_1 = order.address.street;
      customer.postal_code = order.address.postal_code;
      customer.city = order.address.city;
      customer.country = order.address.country;
    }
  }

  const sellerNotes: string[] = [];
  if (tableNumber) sellerNotes.push(`Table ${tableNumber}.`);
  sellerNotes.push(order.payment_status === 'paid' ? 'Commande deja payee sur Yumco.' : 'Paiement a encaisser sur place.');

  const payload: HubriseOrderPayload = {
    channel: 'yumco',
    ref: order.order_number,
    private_ref: String(order.id),
    status: 'new',
    service_type: serviceType(order.type),
    asap: order.requested_time === null,
    items,
    seller_notes: sellerNotes.join(' '),
  };
  if (order.comment) payload.customer_notes = order.comment;
  if (order.requested_time) {
    payload.expected_time = pyIsoUtc(order.requested_time);
    if (order.type === 'delivery') payload.expected_time_pickup = false;
  }
  if (customer) payload.customer = customer;
  if (order.payment_status === 'paid') {
    payload.payments = [
      { name: 'Yumco', ref: 'YUMCO', amount: hubriseMoney(Number(order.amount_total)), info: { payment_status: order.payment_status } },
    ];
  }
  return payload;
};

/** Modification d'une commande déjà envoyée : articles, notes, paiements et heure souhaitée. */
export const buildHubriseOrderPatchPayload = (order: HubriseOrder, tableNumber: string | null) => {
  const base = buildHubriseOrderPayload(order, tableNumber);
  const patch: Record<string, unknown> = {
    items: base.items.map((item) => {
      const patchItem: HubriseItem = { product_name: item.product_name, price: item.price, quantity: item.quantity };
      if (item.customer_notes !== undefined) patchItem.customer_notes = item.customer_notes;
      if (item.options !== undefined) patchItem.options = item.options;
      return patchItem;
    }),
    seller_notes: base.seller_notes,
  };
  if (base.customer_notes !== undefined) patch.customer_notes = base.customer_notes;
  if (base.payments !== undefined) patch.payments = base.payments;
  if (base.expected_time !== undefined) patch.expected_time = base.expected_time;
  if (base.expected_time_pickup !== undefined) patch.expected_time_pickup = base.expected_time_pickup;
  return patch as { items: unknown[] } & Record<string, unknown>;
};
