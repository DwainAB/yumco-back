/**
 * Commandes (order_service.py et la partie « articles » de routes/order.py).
 */
import { randomInt } from 'node:crypto';
import { prisma, type Tx } from '../../db/prisma.js';
import { Prisma } from '../../generated/prisma/client.js';
import { badRequest, notFound } from '../../lib/http-error.js';
import { Decimal, money } from '../../lib/money.js';
import { incrementPromoCodeUsage } from '../promo-codes/promo-codes.service.js';
import type { OrderCreate, OrderItemCreate } from './orders.schemas.js';
import { orderInclude } from './orders.serializers.js';
import {
  assertValidQuantity,
  calculateOrderPricing,
  findAllYouCanEat,
  findMenu,
  findMenuOption,
  findProduct,
  ITEM_REFERENCE_REQUIRED,
  pricingInclude,
  recalculateOrderDeliveryTotals,
} from './pricing.service.js';

export const getOrder = (restaurantId: number, orderId: number) =>
  prisma.order.findFirst({ where: { id: orderId, restaurant_id: restaurantId }, include: orderInclude });

export const findOrderOr404 = async (restaurantId: number, orderId: number) => {
  const order = await getOrder(restaurantId, orderId);
  if (!order) throw notFound('Order not found');
  return order;
};

/** Numéro de commande : « # », initiale du client et 4 chiffres (ex. #M4821). */
export const generateOrderNumber = (firstName: string) => {
  const letter = (firstName[0] ?? 'X').toUpperCase();
  const digits = Array.from({ length: 4 }, () => randomInt(10)).join('');
  return `#${letter}${digits}`;
};

const uniqueOrderNumber = async (firstName: string) => {
  let orderNumber = generateOrderNumber(firstName);
  while (await prisma.order.findFirst({ where: { order_number: orderNumber }, select: { id: true } })) {
    orderNumber = generateOrderNumber(firstName);
  }
  return orderNumber;
};

interface ProcessedItem {
  product_id?: number;
  menu_id?: number;
  all_you_can_eat_id?: number;
  name: string;
  quantity: number;
  /** Prix et sous-total calculés en flottants, comme en Python (arrondis par la base). */
  unit_price: number;
  subtotal: number;
  comment: string | null;
  options: { id: number; name: string; additional_price: number }[];
}

/** Lit les articles demandés et calcule leur prix (même ordre de contrôle et mêmes messages que le Python). */
const processItems = async (restaurantId: number, items: OrderItemCreate[]) => {
  let itemsSubtotal = new Decimal('0.00');
  const processed: ProcessedItem[] = [];
  for (const item of items) {
    if (item.product_id) {
      assertValidQuantity(item.quantity);
      const product = await findProduct(restaurantId, item.product_id);
      if (!product) throw badRequest(`Product ${item.product_id} not found`);
      const unitPrice = Number(product.price);
      const subtotal = unitPrice * item.quantity;
      itemsSubtotal = itemsSubtotal.plus(money(subtotal));
      processed.push({ product_id: item.product_id, name: product.name, quantity: item.quantity, unit_price: unitPrice, subtotal, comment: item.comment ?? null, options: [] });
    } else if (item.menu_id) {
      assertValidQuantity(item.quantity);
      const menu = await findMenu(restaurantId, item.menu_id);
      if (!menu) throw badRequest(`Menu ${item.menu_id} not found`);
      let unitPrice = Number(menu.price);
      const options: ProcessedItem['options'] = [];
      for (const optionId of item.selected_options) {
        const option = await findMenuOption(restaurantId, optionId);
        if (!option) throw badRequest(`MenuOption ${optionId} not found`);
        const additionalPrice = Number(option.additional_price ?? 0);
        unitPrice += additionalPrice;
        options.push({ id: option.id, name: option.name, additional_price: additionalPrice });
      }
      const subtotal = unitPrice * item.quantity;
      itemsSubtotal = itemsSubtotal.plus(money(subtotal));
      processed.push({ menu_id: item.menu_id, name: menu.name, quantity: item.quantity, unit_price: unitPrice, subtotal, comment: item.comment ?? null, options });
    } else if (item.all_you_can_eat_id) {
      assertValidQuantity(item.quantity);
      const offer = await findAllYouCanEat(restaurantId, item.all_you_can_eat_id);
      if (!offer) throw badRequest(`AllYouCanEat offer ${item.all_you_can_eat_id} not found`);
      const unitPrice = Number(offer.price);
      const subtotal = unitPrice * item.quantity;
      itemsSubtotal = itemsSubtotal.plus(money(subtotal));
      processed.push({ all_you_can_eat_id: item.all_you_can_eat_id, name: offer.name, quantity: item.quantity, unit_price: unitPrice, subtotal, comment: item.comment ?? null, options: [] });
    } else {
      throw badRequest(ITEM_REFERENCE_REQUIRED);
    }
  }
  return { itemsSubtotal, processed };
};

const insertItems = async (tx: Tx, orderId: number, items: ProcessedItem[]) => {
  for (const { options, ...item } of items) {
    const created = await tx.orderItem.create({ data: { ...item, order_id: orderId } });
    for (const option of options) {
      await tx.orderItem.create({
        data: {
          order_id: orderId,
          menu_option_id: option.id,
          name: option.name,
          quantity: created.quantity,
          unit_price: option.additional_price,
          subtotal: option.additional_price * created.quantity,
          parent_order_item_id: created.id,
        },
      });
    }
  }
};

const isOrderNumberConflict = (error: unknown) =>
  error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2002' && JSON.stringify(error.meta ?? {}).includes('order_number');

/**
 * Crée une commande (create_order). Tous les contrôles et le calcul du prix sont faits avant d'écrire ;
 * les enregistrements (client, adresse, commande, articles, table, code promo) sont faits en une transaction.
 */
export const createOrder = async (restaurantId: number, data: OrderCreate) => {
  const restaurant = await prisma.restaurant.findFirst({ where: { id: restaurantId, is_deleted: false }, include: pricingInclude });
  if (!restaurant) throw notFound('Restaurant not found');

  if (data.type !== 'onsite' && !data.customer) throw badRequest('Customer is required for delivery and pickup orders');
  if (data.type === 'delivery' && !data.address) throw badRequest('Address is required for delivery orders');
  const deliveryAddress = data.type === 'delivery' ? data.address! : null;

  const firstName = data.customer ? data.customer.first_name : 'X';
  const { itemsSubtotal, processed } = await processItems(restaurantId, data.items);

  if (data.table_id) {
    const table = await prisma.table.findFirst({ where: { id: data.table_id, restaurant_id: restaurantId } });
    if (!table) throw badRequest(`Table ${data.table_id} not found for this restaurant`);
  }

  const pricing = await calculateOrderPricing({
    restaurant,
    orderType: data.type,
    itemsSubtotal,
    address: deliveryAddress,
    promoCode: data.promo_code,
  });

  for (let attempt = 0; ; attempt += 1) {
    const orderNumber = await uniqueOrderNumber(firstName);
    try {
      const orderId = await prisma.$transaction(async (tx) => {
        const customer =
          data.type !== 'onsite' && data.customer
            ? await tx.customer.create({
                data: {
                  restaurant_id: restaurantId,
                  first_name: data.customer.first_name,
                  last_name: data.customer.last_name,
                  email: data.customer.email ?? null,
                  phone: data.customer.phone ?? null,
                },
              })
            : null;
        const address = deliveryAddress ? await tx.address.create({ data: deliveryAddress }) : null;

        if (data.table_id && data.type === 'onsite') await tx.table.update({ where: { id: data.table_id }, data: { is_available: false } });

        const order = await tx.order.create({
          data: {
            order_number: orderNumber,
            restaurant_id: restaurantId,
            customer_id: customer?.id ?? null,
            type: data.type,
            status: 'pending',
            payment_status: 'unpaid',
            is_draft: data.type === 'onsite',
            comment: data.comment ?? null,
            requested_time: data.requested_time ?? null,
            table_id: data.table_id ?? null,
            address_id: address?.id ?? null,
            items_subtotal: pricing.items_subtotal,
            delivery_fee: pricing.delivery_fee,
            delivery_distance_km: pricing.delivery_distance_km,
            promo_code: pricing.promo_code,
            discount_type: pricing.discount_type,
            discount_value: pricing.discount_value,
            discount_amount: pricing.discount_amount,
            amount_before_discount: pricing.amount_before_discount,
            amount_total: pricing.amount_total,
          },
        });
        await insertItems(tx, order.id, processed);
        if (order.promo_code) await incrementPromoCodeUsage(restaurantId, order.promo_code, tx);
        return order.id;
      });
      return await prisma.order.findUniqueOrThrow({ where: { id: orderId }, include: orderInclude });
    } catch (error) {
      // Deux commandes ont tiré le même numéro au même moment : on en tire un autre.
      if (isOrderNumberConflict(error) && attempt < 5) continue;
      throw error;
    }
  }
};

/** Totaux après modification des articles : recalcul complet pour une livraison, simple addition sinon. */
const refreshOrderTotals = async (tx: Tx, orderId: number, simpleTotals: { items_subtotal: number; delivery_fee: number }) => {
  // Lectures séparées : dans une transaction, Prisma enverrait les relations en parallèle sur la même connexion.
  const order = await tx.order.findUniqueOrThrow({ where: { id: orderId } });
  if (order.type === 'delivery') {
    const items = await tx.orderItem.findMany({ where: { order_id: orderId }, orderBy: { id: 'asc' } });
    const address = order.address_id !== null ? await tx.address.findUnique({ where: { id: order.address_id } }) : null;
    const totals = await recalculateOrderDeliveryTotals({ ...order, items, address }, tx);
    await tx.order.update({ where: { id: orderId }, data: totals });
  } else {
    // Comme en Python : la remise n'est pas reprise dans ce calcul.
    await tx.order.update({
      where: { id: orderId },
      data: { items_subtotal: simpleTotals.items_subtotal, amount_total: simpleTotals.items_subtotal + simpleTotals.delivery_fee },
    });
  }
};

/**
 * Ajoute des articles à une commande existante (add_order_items) : un produit ou une formule déjà présent
 * voit sa quantité augmenter, un menu ajoute toujours une nouvelle ligne avec ses options.
 */
export const addOrderItems = async (restaurantId: number, orderId: number, items: OrderItemCreate[]) => {
  const order = await prisma.order.findFirst({ where: { id: orderId, restaurant_id: restaurantId } });
  if (!order) throw notFound('Order not found');

  await prisma.$transaction(
    async (tx) => {
      let addedTotal = 0;
      for (const item of items) {
        if (item.product_id || item.all_you_can_eat_id) {
          assertValidQuantity(item.quantity);
          const isProduct = Boolean(item.product_id);
          const reference = isProduct
            ? await findProduct(restaurantId, item.product_id!, tx)
            : await findAllYouCanEat(restaurantId, item.all_you_can_eat_id!, tx);
          if (!reference) {
            throw badRequest(isProduct ? `Product ${item.product_id} not found` : `AllYouCanEat ${item.all_you_can_eat_id} not found`);
          }
          const unitPrice = Number(reference.price);
          const link = isProduct ? { product_id: item.product_id! } : { all_you_can_eat_id: item.all_you_can_eat_id! };
          const existing = await tx.orderItem.findFirst({
            where: { order_id: order.id, parent_order_item_id: null, ...link },
            orderBy: { id: 'asc' },
          });
          if (existing) {
            const quantity = existing.quantity + item.quantity;
            await tx.orderItem.update({ where: { id: existing.id }, data: { quantity, subtotal: Number(existing.unit_price) * quantity } });
            addedTotal += unitPrice * item.quantity;
          } else {
            const subtotal = unitPrice * item.quantity;
            addedTotal += subtotal;
            await tx.orderItem.create({
              data: { order_id: order.id, ...link, name: reference.name, quantity: item.quantity, unit_price: unitPrice, subtotal, comment: item.comment ?? null },
            });
          }
        } else if (item.menu_id) {
          assertValidQuantity(item.quantity);
          const menu = await findMenu(restaurantId, item.menu_id, tx);
          if (!menu) throw badRequest(`Menu ${item.menu_id} not found`);
          let unitPrice = Number(menu.price);
          const options = [];
          for (const optionId of item.selected_options) {
            const option = await findMenuOption(restaurantId, optionId, tx);
            if (!option) throw badRequest(`MenuOption ${optionId} not found`);
            unitPrice += Number(option.additional_price ?? 0);
            options.push(option);
          }
          const subtotal = unitPrice * item.quantity;
          addedTotal += subtotal;
          const parent = await tx.orderItem.create({
            data: { order_id: order.id, menu_id: item.menu_id, name: menu.name, quantity: item.quantity, unit_price: unitPrice, subtotal, comment: item.comment ?? null },
          });
          for (const option of options) {
            const additionalPrice = Number(option.additional_price ?? 0);
            await tx.orderItem.create({
              data: {
                order_id: order.id,
                menu_option_id: option.id,
                name: option.name,
                quantity: item.quantity,
                unit_price: additionalPrice,
                subtotal: additionalPrice * item.quantity,
                parent_order_item_id: parent.id,
              },
            });
          }
        } else {
          throw badRequest(ITEM_REFERENCE_REQUIRED);
        }
      }
      await refreshOrderTotals(tx, order.id, {
        items_subtotal: Number(order.items_subtotal) + addedTotal,
        delivery_fee: Number(order.delivery_fee),
      });
    },
    { timeout: 30_000 },
  );
  return findOrderOr404(restaurantId, orderId);
};

/** Retire une unité d'un article (ou la ligne entière s'il n'en reste qu'une), options comprises (remove_order_item). */
export const removeOrderItem = async (restaurantId: number, orderId: number, itemId: number) => {
  const order = await prisma.order.findFirst({ where: { id: orderId, restaurant_id: restaurantId } });
  if (!order) throw notFound('Order not found');
  const item = await prisma.orderItem.findFirst({ where: { id: itemId, order_id: orderId } });
  if (!item) throw notFound('Item not found');

  await prisma.$transaction(
    async (tx) => {
      const isRoot = item.parent_order_item_id === null;
      const children = isRoot ? await tx.orderItem.findMany({ where: { parent_order_item_id: item.id }, orderBy: { id: 'asc' } }) : [];
      let itemsSubtotal = Number(order.items_subtotal);

      if (item.quantity > 1) {
        const quantity = item.quantity - 1;
        await tx.orderItem.update({ where: { id: item.id }, data: { quantity, subtotal: Number(item.unit_price) * quantity } });
        if (isRoot) itemsSubtotal -= Number(item.unit_price);
        for (const child of children) {
          await tx.orderItem.update({ where: { id: child.id }, data: { quantity, subtotal: Number(child.unit_price) * quantity } });
        }
      } else {
        if (isRoot) itemsSubtotal -= Number(item.subtotal);
        await tx.orderItem.deleteMany({ where: { id: { in: [...children.map((child) => child.id), item.id] } } });
      }

      if (order.type === 'delivery') {
        await refreshOrderTotals(tx, order.id, { items_subtotal: itemsSubtotal, delivery_fee: Number(order.delivery_fee) });
      } else {
        await tx.order.update({
          where: { id: order.id },
          data: { items_subtotal: itemsSubtotal, amount_total: itemsSubtotal + Number(order.delivery_fee) },
        });
      }
    },
    { timeout: 30_000 },
  );
  return findOrderOr404(restaurantId, orderId);
};
