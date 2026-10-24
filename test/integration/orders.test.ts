/** Commandes (tests/integration/test_orders.py). */
import { beforeEach, describe, expect, it } from 'vitest';
import { api, authHeaders, makeCategory, makeProduct, makeRestaurant, makeUser, prisma } from '../helpers.js';

let ctx: { userEmail: string; restaurantId: number; productId: number };

beforeEach(async () => {
  const user = await makeUser({ email: 'owner_orders@test.com' });
  const restaurant = await makeRestaurant(user.id);
  const category = await makeCategory(restaurant.id);
  const product = await makeProduct(restaurant.id, category.id, 'Burger', 12.5);
  ctx = { userEmail: user.email, restaurantId: restaurant.id, productId: product.id };
});

const pickup = (quantity: number, customer: Record<string, string>, extra: Record<string, unknown> = {}) =>
  api()
    .post(`/restaurants/${ctx.restaurantId}/orders`)
    .send({ type: 'pickup', items: [{ product_id: ctx.productId, quantity }], customer, ...extra });

describe('orders', () => {
  it('create pickup order', async () => {
    const res = await pickup(2, { first_name: 'Jane', last_name: 'Doe', phone: '+33600000002', email: 'jane@test.com' });
    expect(res.status).toBe(201);
    expect(res.body.type).toBe('pickup');
    expect(res.body.status).toBe('pending');
    expect(res.body.items_subtotal).toBe(25);
    expect(res.body.order_number).toMatch(/^#J\d{4}$/);
  });

  it('wrong product', async () => {
    const res = await api()
      .post(`/restaurants/${ctx.restaurantId}/orders`)
      .send({ type: 'pickup', items: [{ product_id: 99999, quantity: 1 }], customer: { first_name: 'Jane', last_name: 'Doe', phone: '+33600000003' } });
    expect(res.status).toBe(400);
    expect(res.body.detail).toBe('Product 99999 not found');
  });

  it('update order status', async () => {
    const created = await pickup(1, { first_name: 'Jane', last_name: 'Doe', phone: '+33600000004' });
    expect(created.status).toBe(201);
    const res = await api()
      .post(`/restaurants/${ctx.restaurantId}/orders/${created.body.id}/status`)
      .set(await authHeaders(ctx.userEmail))
      .send({ status: 'preparing' });
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('preparing');
    expect(res.body.prepared_by_user.first_name).toBe('Test');
  });

  it('list orders', async () => {
    for (const i of [0, 1]) await pickup(1, { first_name: 'Jane', last_name: 'Doe', phone: `+3360000100${i}` });
    const res = await api().get(`/restaurants/${ctx.restaurantId}/orders`).set(await authHeaders(ctx.userEmail));
    expect(res.status).toBe(200);
    expect(res.body.length).toBeGreaterThanOrEqual(2);
  });

  it('delete draft onsite order', async () => {
    const created = await api().post(`/restaurants/${ctx.restaurantId}/orders`).send({ type: 'onsite', items: [{ product_id: ctx.productId, quantity: 1 }] });
    expect(created.status).toBe(201);
    const res = await api().delete(`/restaurants/${ctx.restaurantId}/orders/${created.body.id}`).set(await authHeaders(ctx.userEmail));
    expect(res.status).toBe(204);
  });

  it('total calculation', async () => {
    const res = await pickup(3, { first_name: 'Jane', last_name: 'Doe', phone: '+33600000005' });
    expect(res.status).toBe(201);
    expect(res.body.items_subtotal).toBe(37.5);
    expect(res.body.amount_total).toBe(37.5);
  });

  it('validate promo code', async () => {
    await prisma.restaurantPromoCode.create({
      data: { restaurant_id: ctx.restaurantId, code: 'YUM10', discount_type: 'percent', discount_value: 10, is_active: true, usage_count: 0 },
    });
    const res = await api()
      .post(`/restaurants/${ctx.restaurantId}/promo-codes/validate`)
      .send({ promo_code: 'yum10', type: 'pickup', items: [{ product_id: ctx.productId, quantity: 2 }] });
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ promo_code: 'YUM10', items_subtotal: 25, discount_amount: 2.5, amount_total: 22.5 });
  });

  it('pickup order with promo code', async () => {
    await prisma.restaurantPromoCode.create({
      data: { restaurant_id: ctx.restaurantId, code: 'EURO5', discount_type: 'fixed', discount_value: 5, is_active: true, usage_count: 0 },
    });
    const res = await pickup(2, { first_name: 'Jane', last_name: 'Doe', phone: '+33600000007', email: 'jane-promo@test.com' }, { promo_code: 'EURO5' });
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({ promo_code: 'EURO5', amount_before_discount: 25, discount_amount: 5, amount_total: 20 });
    const promo = await prisma.restaurantPromoCode.findFirstOrThrow({ where: { code: 'EURO5' } });
    expect(promo.usage_count).toBe(1);
  });

  it('export csv for a selected month', async () => {
    const first = await pickup(2, { first_name: 'Jane', last_name: 'Doe', phone: '+33600000008', email: 'jane-csv@test.com' });
    const second = await api()
      .post(`/restaurants/${ctx.restaurantId}/orders`)
      .send({
        type: 'delivery',
        items: [{ product_id: ctx.productId, quantity: 1 }],
        customer: { first_name: 'John', last_name: 'Smith', phone: '+33600000009', email: 'john-csv@test.com' },
        address: { street: '2 Rue du Test', city: 'Paris', postal_code: '75002', country: 'FR' },
      });
    expect(first.status).toBe(201);
    expect(second.status).toBe(201);

    await prisma.order.update({
      where: { id: first.body.id },
      data: { status: 'completed', payment_status: 'paid', completed_at: new Date(Date.UTC(2026, 4, 10, 12, 30)), created_at: new Date(Date.UTC(2026, 4, 10, 10)) },
    });
    await prisma.order.update({
      where: { id: second.body.id },
      data: { status: 'completed', payment_status: 'paid', completed_at: new Date(Date.UTC(2026, 5, 3, 12, 30)), created_at: new Date(Date.UTC(2026, 5, 3, 10)) },
    });

    const res = await api().get(`/restaurants/${ctx.restaurantId}/orders/export?format=csv&month=5&year=2026`).set(await authHeaders(ctx.userEmail));
    expect(res.status).toBe(200);
    expect(res.headers['content-type']).toMatch(/^text\/csv/);
    const body = res.text;
    expect(body.startsWith('﻿')).toBe(true);
    expect(body).toContain('Restaurant;Test Restaurant');
    expect(body).toContain(first.body.order_number);
    expect(body).not.toContain(second.body.order_number);
    expect(body).toContain('2x Burger');
    // Heure locale du restaurant (Paris, UTC+2 en mai).
    expect(body).toContain('10/05/2026 12:00');
  });

  it('export pdf returns a pdf file', async () => {
    const created = await api().post(`/restaurants/${ctx.restaurantId}/orders`).send({ type: 'onsite', items: [{ product_id: ctx.productId, quantity: 1 }] });
    expect(created.status).toBe(201);
    await prisma.order.update({
      where: { id: created.body.id },
      data: { status: 'completed', payment_status: 'paid', completed_at: new Date(Date.UTC(2026, 4, 12, 20)) },
    });
    const res = await api()
      .get(`/restaurants/${ctx.restaurantId}/orders/export?format=pdf`)
      .set(await authHeaders(ctx.userEmail))
      .buffer(true)
      .parse((response, callback) => {
        const chunks: Buffer[] = [];
        response.on('data', (chunk: Buffer) => chunks.push(chunk));
        response.on('end', () => callback(null, Buffer.concat(chunks)));
      });
    expect(res.status).toBe(200);
    expect(res.headers['content-type']).toBe('application/pdf');
    expect(res.headers['content-disposition']).toMatch(/\.pdf"$/);
    expect((res.body as Buffer).subarray(0, 4).toString()).toBe('%PDF');
  });

  it('export requires a complete date range', async () => {
    const res = await api().get(`/restaurants/${ctx.restaurantId}/orders/export?format=csv&date_from=2026-05-01`).set(await authHeaders(ctx.userEmail));
    expect(res.status).toBe(400);
    expect(res.body.detail).toBe('date_from and date_to must be provided together');
  });

  it('list orders by custom date range', async () => {
    const first = await pickup(1, { first_name: 'Jane', last_name: 'Doe', phone: '+33600000010' });
    const second = await pickup(1, { first_name: 'John', last_name: 'Smith', phone: '+33600000011' });
    await prisma.order.update({ where: { id: first.body.id }, data: { status: 'completed', created_at: new Date(Date.UTC(2026, 4, 4, 12)) } });
    await prisma.order.update({ where: { id: second.body.id }, data: { status: 'completed', created_at: new Date(Date.UTC(2026, 5, 8, 12)) } });

    const res = await api()
      .get(`/restaurants/${ctx.restaurantId}/orders?status=completed&date_from=2026-05-01&date_to=2026-05-31`)
      .set(await authHeaders(ctx.userEmail));
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(1);
    expect(res.body[0].id).toBe(first.body.id);
  });
});
