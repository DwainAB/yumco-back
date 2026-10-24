/** Ajout et retrait d'articles d'une commande (tests/integration/test_order_items.py). */
import { beforeEach, describe, expect, it } from 'vitest';
import { api, authHeaders, makeCategory, makeProduct, makeRestaurant, makeUser } from '../helpers.js';

let ctx: { headers: Record<string, string>; restaurantId: number; burgerId: number; friesId: number };

beforeEach(async () => {
  const user = await makeUser({ email: 'owner_items@test.com' });
  const restaurant = await makeRestaurant(user.id);
  const category = await makeCategory(restaurant.id);
  const burger = await makeProduct(restaurant.id, category.id, 'Burger', 12.0);
  const fries = await makeProduct(restaurant.id, category.id, 'Frites', 4.0);
  ctx = { headers: await authHeaders(user.email), restaurantId: restaurant.id, burgerId: burger.id, friesId: fries.id };
});

const onsiteOrder = (items: { product_id: number; quantity: number }[]) =>
  api().post(`/restaurants/${ctx.restaurantId}/orders`).send({ type: 'onsite', items });

type Item = { id: number; product_id: number | null; parent_order_item_id: number | null; quantity: number };

describe('order items', () => {
  it('adds an item to an existing order', async () => {
    const order = await onsiteOrder([{ product_id: ctx.burgerId, quantity: 1 }]);
    expect(order.status).toBe(201);
    expect(order.body.items_subtotal).toBe(12);
    const res = await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.body.id}/items`).set(ctx.headers).send([{ product_id: ctx.friesId, quantity: 2 }]);
    expect(res.status).toBe(200);
    expect(res.body.items_subtotal).toBe(20);
  });

  it('adding the same product increments its quantity', async () => {
    const order = await onsiteOrder([{ product_id: ctx.burgerId, quantity: 1 }]);
    const res = await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.body.id}/items`).set(ctx.headers).send([{ product_id: ctx.burgerId, quantity: 1 }]);
    expect(res.status).toBe(200);
    const burger = (res.body.items as Item[]).find((i) => i.product_id === ctx.burgerId && i.parent_order_item_id === null)!;
    expect(burger.quantity).toBe(2);
    expect(res.body.items_subtotal).toBe(24);
  });

  it('removing an item decrements its quantity', async () => {
    const order = await onsiteOrder([{ product_id: ctx.burgerId, quantity: 3 }]);
    const itemId = order.body.items[0].id;
    const res = await api().delete(`/restaurants/${ctx.restaurantId}/orders/${order.body.id}/items/${itemId}`).set(ctx.headers);
    expect(res.status).toBe(200);
    expect((res.body.items as Item[]).find((i) => i.id === itemId)!.quantity).toBe(2);
    expect(res.body.items_subtotal).toBe(24);
  });

  it('removing the last unit deletes the item', async () => {
    const order = await onsiteOrder([
      { product_id: ctx.burgerId, quantity: 1 },
      { product_id: ctx.friesId, quantity: 1 },
    ]);
    const friesItem = (order.body.items as Item[]).find((i) => i.product_id === ctx.friesId)!;
    const res = await api().delete(`/restaurants/${ctx.restaurantId}/orders/${order.body.id}/items/${friesItem.id}`).set(ctx.headers);
    expect(res.status).toBe(200);
    expect((res.body.items as Item[]).map((i) => i.id)).not.toContain(friesItem.id);
    expect(res.body.items_subtotal).toBe(12);
  });

  it('adding an invalid product returns 400', async () => {
    const order = await onsiteOrder([{ product_id: ctx.burgerId, quantity: 1 }]);
    const res = await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.body.id}/items`).set(ctx.headers).send([{ product_id: 99999, quantity: 1 }]);
    expect(res.status).toBe(400);
  });
});
