/** Demandes d'avis Google (tests/integration/test_review_followups.py). */
import { afterEach, describe, expect, it } from 'vitest';
import { env } from '../../src/config/env.js';
import { api, authHeaders, makeCategory, makeProduct, makeRestaurant, makeUser, prisma } from '../helpers.js';

const setup = async (email: string) => {
  const user = await makeUser({ email });
  const restaurant = await makeRestaurant(user.id);
  await prisma.restaurant.update({ where: { id: restaurant.id }, data: { google_review_url: 'https://g.page/r/test/review' } });
  const category = await makeCategory(restaurant.id);
  const product = await makeProduct(restaurant.id, category.id);
  return { headers: await authHeaders(email), restaurantId: restaurant.id, productId: product.id };
};

const createOrder = async (restaurantId: number, productId: number, email: string) => {
  const res = await api()
    .post(`/restaurants/${restaurantId}/orders`)
    .send({ type: 'pickup', items: [{ product_id: productId, quantity: 1 }], customer: { first_name: 'Jane', last_name: 'Doe', phone: '+33600000099', email } });
  expect(res.status).toBe(201);
  return res.body.id as number;
};

afterEach(() => {
  env.REVIEW_FOLLOWUPS_CRON_SECRET = null;
});

describe('review followups', () => {
  it('a completed order schedules a review request 24 h later', async () => {
    const ctx = await setup('owner_followup@test.com');
    const orderId = await createOrder(ctx.restaurantId, ctx.productId, 'review@test.com');
    const res = await api().post(`/restaurants/${ctx.restaurantId}/orders/${orderId}/status`).set(ctx.headers).send({ status: 'completed' });
    expect(res.status).toBe(200);

    const followup = await prisma.reviewFollowup.findFirstOrThrow({ where: { order_id: orderId } });
    expect(followup.status).toBe('pending');
    expect(followup.customer_email).toBe('review@test.com');
    const delta = followup.send_at.getTime() - new Date(res.body.completed_at).getTime();
    expect(delta).toBeGreaterThan((23 * 60 + 59) * 60_000);
    expect(delta).toBeLessThan((24 * 60 + 1) * 60_000);
  });

  it('the internal route sends due requests', async () => {
    env.REVIEW_FOLLOWUPS_CRON_SECRET = 'super-secret';
    const ctx = await setup('owner_process@test.com');
    const orderId = await createOrder(ctx.restaurantId, ctx.productId, 'process@test.com');
    expect((await api().post(`/restaurants/${ctx.restaurantId}/orders/${orderId}/status`).set(ctx.headers).send({ status: 'completed' })).status).toBe(200);
    const followup = await prisma.reviewFollowup.findFirstOrThrow({ where: { order_id: orderId } });
    await prisma.reviewFollowup.update({ where: { id: followup.id }, data: { send_at: new Date(Date.now() - 60_000) } });

    expect((await api().post('/internal/review-followups/process').set('X-Cron-Secret', 'wrong')).status).toBe(401);
    const res = await api().post('/internal/review-followups/process').set('X-Cron-Secret', 'super-secret');
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ processed: 1, sent: 1, failed: 0, cancelled: 0 });
    const sent = await prisma.reviewFollowup.findUniqueOrThrow({ where: { id: followup.id } });
    expect(sent.status).toBe('sent');
    expect(sent.sent_at).not.toBeNull();
  });

  it('without a configured secret the route refuses to run', async () => {
    const res = await api().post('/internal/review-followups/process');
    expect(res.status).toBe(500);
    expect(res.body.detail).toBe('REVIEW_FOLLOWUPS_CRON_SECRET is not configured');
  });
});
