/** Clients (tests/integration/test_customers.py). */
import { beforeEach, describe, expect, it } from 'vitest';
import { api, authHeaders, makeCategory, makeProduct, makeRestaurant, makeUser } from '../helpers.js';

let ctx: { headers: Record<string, string>; restaurantId: number; productId: number };

beforeEach(async () => {
  const user = await makeUser({ email: 'owner_customers@test.com' });
  const restaurant = await makeRestaurant(user.id);
  const category = await makeCategory(restaurant.id);
  const product = await makeProduct(restaurant.id, category.id, 'Burger', 10.0);
  ctx = { headers: await authHeaders(user.email), restaurantId: restaurant.id, productId: product.id };
});

const orderWithCustomer = (phone: string, email?: string) =>
  api()
    .post(`/restaurants/${ctx.restaurantId}/orders`)
    .send({
      type: 'pickup',
      items: [{ product_id: ctx.productId, quantity: 1 }],
      customer: { first_name: 'Jane', last_name: 'Doe', phone, ...(email ? { email } : {}) },
    });

const customers = async () => (await api().get(`/restaurants/${ctx.restaurantId}/customers`).set(ctx.headers)).body;

describe('customers', () => {
  it('a customer is created with the first order', async () => {
    await orderWithCustomer('+33600000060');
    const list = await customers();
    expect(list).toHaveLength(1);
    expect(list[0].phone).toBe('+33600000060');
  });

  it('each order creates a customer', async () => {
    await orderWithCustomer('+33600000061');
    await orderWithCustomer('+33600000061');
    expect(await customers()).toHaveLength(2);
  });

  it('gets a customer', async () => {
    await orderWithCustomer('+33600000062');
    const customerId = (await customers())[0].id;
    const res = await api().get(`/restaurants/${ctx.restaurantId}/customers/${customerId}`).set(ctx.headers);
    expect(res.status).toBe(200);
    expect(res.body.id).toBe(customerId);
  });

  it('updates a customer', async () => {
    await orderWithCustomer('+33600000063');
    const customerId = (await customers())[0].id;
    const res = await api().put(`/restaurants/${ctx.restaurantId}/customers/${customerId}`).set(ctx.headers).send({ first_name: 'Marie', last_name: 'Martin' });
    expect(res.status).toBe(200);
    expect(res.body.first_name).toBe('Marie');
    expect(res.body.updated_at).not.toBeNull();
  });

  it('deletes a customer', async () => {
    await orderWithCustomer('+33600000064');
    const customerId = (await customers())[0].id;
    expect((await api().delete(`/restaurants/${ctx.restaurantId}/customers/${customerId}`).set(ctx.headers)).status).toBe(204);
    expect((await customers()).every((c: { id: number }) => c.id !== customerId)).toBe(true);
  });
});
