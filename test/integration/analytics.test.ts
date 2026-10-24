/** Statistiques (tests/integration/test_analytics.py). */
import { beforeEach, describe, expect, it } from 'vitest';
import { api, authHeaders, makeCategory, makeProduct, makeRestaurant, makeUser } from '../helpers.js';

let ctx: { headers: Record<string, string>; restaurantId: number; productId: number };

beforeEach(async () => {
  const user = await makeUser({ email: 'owner_analytics@test.com' });
  const restaurant = await makeRestaurant(user.id);
  const category = await makeCategory(restaurant.id);
  const product = await makeProduct(restaurant.id, category.id, 'Burger', 15.0);
  ctx = { headers: await authHeaders(user.email), restaurantId: restaurant.id, productId: product.id };
});

const createOrder = (quantity = 1, phone = '+33600000050') =>
  api()
    .post(`/restaurants/${ctx.restaurantId}/orders`)
    .send({ type: 'pickup', items: [{ product_id: ctx.productId, quantity }], customer: { first_name: 'Test', last_name: 'Client', phone } });

const get = (path: string) => api().get(`/restaurants/${ctx.restaurantId}/${path}`).set(ctx.headers);

describe('analytics', () => {
  it('order analytics', async () => {
    await createOrder();
    const res = await get('orders/analytics');
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ monthly_orders_count: 1, monthly_orders_change: 1, monthly_orders_change_percentage: 100, pickup_percentage: 100, delivery_percentage: 0 });
    expect(res.body.top_items).toEqual([{ item_name: 'Burger', item_type: 'product', quantity_sold: 1, revenue: 15 }]);
    expect(res.body.repeat_purchase).toEqual({ rate_percentage: 0, repeat_customers: 0, identifiable_customers: 1 });
  });

  it('revenue analytics', async () => {
    await createOrder(2);
    const res = await get('revenue/analytics');
    expect(res.status).toBe(200);
    expect(res.body.current_month_amount).toBe(30);
    expect(res.body.yearly_channels).toHaveLength(1);
    expect(res.body.yearly_channels[0].pickup).toEqual({ amount: 30, percentage: 100 });
    expect(res.body.best_month.amount).toBe(30);
    expect(res.body.best_day.label).toMatch(/^\d{1,2} [A-Za-z]+ \d{4}$/);
  });

  it('performance analytics', async () => {
    const res = await get('performance/analytics');
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ preparation_time: { average_minutes: 0, difference_vs_previous_month_minutes: 0 }, preparers: [] });
  });

  it('customer analytics', async () => {
    await createOrder(1, '+33600000051');
    await createOrder(1, '+33600000052');
    // Même client écrit différemment : reconnu grâce aux chiffres du téléphone.
    await createOrder(1, '+33 6 00 00 00 52');
    const res = await get('customers/analytics');
    expect(res.status).toBe(200);
    expect(res.body.total_customers.total).toBe(2);
    expect(res.body.loyal_customers.total).toBe(1);
    expect(res.body.top_customers[0]).toMatchObject({ identity: '33600000052', orders_count: 2, total_spent: 30 });
  });

  it('works without any order', async () => {
    for (const path of ['orders/analytics', 'revenue/analytics', 'performance/analytics', 'customers/analytics']) {
      expect((await get(path)).status).toBe(200);
    }
  });
});
