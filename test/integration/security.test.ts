/**
 * Corrections de sécurité (PLAN_MIGRATION.md §8), actives avec STRICT_RESTAURANT_ACCESS=true.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { env } from '../../src/config/env.js';
import { api, authHeaders, makeCategory, makeProduct, makeRestaurant, makeUser, prisma } from '../helpers.js';

let ctx: {
  mine: number;
  other: number;
  myProduct: number;
  otherProduct: number;
  owner: Record<string, string>;
  admin: Record<string, string>;
};

beforeEach(async () => {
  const owner = await makeUser({ email: 'owner@test.com' });
  const otherOwner = await makeUser({ email: 'other@test.com' });
  await makeUser({ email: 'admin@test.com', isAdmin: true });
  const mine = await makeRestaurant(owner.id, 'Le mien');
  const other = await makeRestaurant(otherOwner.id, "L'autre");
  const myCategory = await makeCategory(mine.id);
  const otherCategory = await makeCategory(other.id);
  ctx = {
    mine: mine.id,
    other: other.id,
    myProduct: (await makeProduct(mine.id, myCategory.id)).id,
    otherProduct: (await makeProduct(other.id, otherCategory.id)).id,
    owner: await authHeaders('owner@test.com'),
    admin: await authHeaders('admin@test.com'),
  };
});

afterEach(() => {
  env.STRICT_RESTAURANT_ACCESS = true;
});

describe('restaurant access', () => {
  it.each(['orders', 'customers', 'users', 'tables', 'reservations', 'promo-codes', 'orders/analytics', 'revenue/analytics'])(
    "an account cannot read another restaurant's %s",
    async (path) => {
      const res = await api().get(`/restaurants/${ctx.other}/${path}`).set(ctx.owner);
      expect(res.status).toBe(403);
      expect(res.body.detail).toBe('Not allowed');
    },
  );

  it('an account reads its own restaurant', async () => {
    expect((await api().get(`/restaurants/${ctx.mine}/orders`).set(ctx.owner)).status).toBe(200);
  });

  it('an admin reads every restaurant', async () => {
    expect((await api().get(`/restaurants/${ctx.other}/orders`).set(ctx.admin)).status).toBe(200);
  });

  it("an account cannot modify another restaurant", async () => {
    expect((await api().put(`/restaurants/${ctx.other}`).set(ctx.owner).send({ name: 'pirate' })).status).toBe(403);
  });

  it('a non-admin cannot change the plan or the AI quotas, but can send them back unchanged', async () => {
    expect((await api().put(`/restaurants/${ctx.mine}`).set(ctx.owner).send({ subscription_plan: 'business_ai' })).status).toBe(403);
    expect((await api().put(`/restaurants/${ctx.mine}`).set(ctx.owner).send({ ai_monthly_quota: 99999 })).status).toBe(403);
    const unchanged = await api().put(`/restaurants/${ctx.mine}`).set(ctx.owner).send({ name: 'Renommé', subscription_plan: 'starter', ai_monthly_quota: 100, stripe_id: null });
    expect(unchanged.status).toBe(200);
    expect(unchanged.body.name).toBe('Renommé');
  });

  it('the Python behaviour is available with STRICT_RESTAURANT_ACCESS=false', async () => {
    env.STRICT_RESTAURANT_ACCESS = false;
    expect((await api().get(`/restaurants/${ctx.other}/orders`).set(ctx.owner)).status).toBe(200);
  });
});

describe('admin and debug routes', () => {
  it('/admin/users/{id} requires an admin', async () => {
    expect((await api().get('/admin/users/1').set(ctx.owner)).status).toBe(403);
    expect((await api().get('/admin/users/1').set(ctx.admin)).status).toBe(200);
  });

  it('/test-email requires an admin', async () => {
    expect((await api().get('/test-email?email=x@test.com')).status).toBe(401);
    expect((await api().get('/test-email?email=x@test.com').set(ctx.owner)).status).toBe(403);
    expect((await api().get('/test-email?email=x@test.com').set(ctx.admin)).status).toBe(200);
  });

  it('the AI web search test requires an account', async () => {
    expect((await api().post(`/restaurants/${ctx.mine}/ai/debug/web-search`).send({ message: 'tendance' })).status).toBe(401);
  });
});

describe('orders', () => {
  const customer = { first_name: 'A', last_name: 'B' };

  it("a product of another restaurant is refused", async () => {
    const res = await api().post(`/restaurants/${ctx.mine}/orders`).send({ type: 'pickup', customer, items: [{ product_id: ctx.otherProduct }] });
    expect(res.status).toBe(400);
    expect(res.body.detail).toBe(`Product ${ctx.otherProduct} not found`);
  });

  it('a negative quantity is refused', async () => {
    const res = await api().post(`/restaurants/${ctx.mine}/orders`).send({ type: 'pickup', customer, items: [{ product_id: ctx.myProduct, quantity: -2 }] });
    expect(res.status).toBe(400);
    expect(await prisma.order.count()).toBe(0);
  });

  it('an unsigned Stripe event is refused', async () => {
    const res = await api().post('/stripe/webhooks').send({ type: 'charge.succeeded', data: { object: { metadata: { order_id: '1' } } } });
    expect(res.status).toBe(400);
    expect(res.body.detail).toBe('Invalid Stripe signature');
  });
});

describe('role changes', () => {
  it("an owner cannot change the role of another restaurant's user", async () => {
    const staff = await makeUser({ email: 'staff@test.com' });
    await prisma.role.create({ data: { user_id: staff.id, restaurant_id: ctx.other, type: 'staff' } });
    const res = await api().put(`/auth/users/${staff.id}`).set(ctx.owner).send({ role: 'owner' });
    expect(res.status).toBe(403);
  });

  it("an owner can change the role of their own staff", async () => {
    const staff = await makeUser({ email: 'mystaff@test.com' });
    await prisma.role.create({ data: { user_id: staff.id, restaurant_id: ctx.mine, type: 'staff' } });
    const res = await api().put(`/auth/users/${staff.id}`).set(ctx.owner).send({ role: 'manager' });
    expect(res.status).toBe(200);
    expect(res.body.roles).toEqual([{ restaurant_id: ctx.mine, type: 'manager' }]);
  });
});
