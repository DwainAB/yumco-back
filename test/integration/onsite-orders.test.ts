/** Commandes sur place : brouillon, envoi, statuts (tests/integration/test_onsite_orders.py). */
import { beforeEach, describe, expect, it } from 'vitest';
import { api, authHeaders, makeCategory, makeProduct, makeRestaurant, makeUser } from '../helpers.js';

let ctx: { headers: Record<string, string>; restaurantId: number; productId: number };

beforeEach(async () => {
  const user = await makeUser({ email: 'owner_onsite@test.com' });
  const restaurant = await makeRestaurant(user.id);
  const category = await makeCategory(restaurant.id);
  const product = await makeProduct(restaurant.id, category.id, 'Burger', 10.0);
  ctx = { headers: await authHeaders(user.email), restaurantId: restaurant.id, productId: product.id };
});

const createOnsite = async (quantity = 1) =>
  (await api().post(`/restaurants/${ctx.restaurantId}/orders`).send({ type: 'onsite', items: [{ product_id: ctx.productId, quantity }] })).body;

describe('onsite orders', () => {
  it('is a draft by default', async () => {
    const order = await createOnsite();
    expect(order.is_draft).toBe(true);
    expect(order.status).toBe('pending');
  });

  it('submit', async () => {
    const order = await createOnsite();
    const res = await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.id}/submit`).set(ctx.headers);
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ id: order.id, status: 'pending', is_draft: false });
  });

  it('cannot submit twice', async () => {
    const order = await createOnsite();
    await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.id}/submit`).set(ctx.headers);
    const res = await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.id}/submit`).set(ctx.headers);
    expect(res.status).toBe(400);
    expect(res.body.detail).toBe('Order is already submitted');
  });

  it('a status change on a draft without HubRise submits it', async () => {
    const order = await createOnsite();
    const res = await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.id}/status`).set(ctx.headers).send({ status: 'preparing' });
    expect(res.status).toBe(200);
    expect(res.body.is_draft).toBe(false);
    expect(res.body.status).toBe('preparing');
  });

  it('full lifecycle', async () => {
    const order = await createOnsite(2);
    await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.id}/submit`).set(ctx.headers);
    let res = await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.id}/status`).set(ctx.headers).send({ status: 'preparing' });
    expect(res.body.status).toBe('preparing');
    res = await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.id}/status`).set(ctx.headers).send({ status: 'completed' });
    expect(res.body.status).toBe('completed');
    expect(res.body.completed_at).not.toBeNull();
  });

  it('a draft can be deleted, a submitted order cannot', async () => {
    const draft = await createOnsite();
    expect((await api().delete(`/restaurants/${ctx.restaurantId}/orders/${draft.id}`).set(ctx.headers)).status).toBe(204);
    const submitted = await createOnsite();
    await api().post(`/restaurants/${ctx.restaurantId}/orders/${submitted.id}/submit`).set(ctx.headers);
    const res = await api().delete(`/restaurants/${ctx.restaurantId}/orders/${submitted.id}`).set(ctx.headers);
    expect(res.status).toBe(400);
  });
});
