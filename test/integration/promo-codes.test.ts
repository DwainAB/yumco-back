/** Codes promo (tests/integration/test_promo_codes.py et test_order_errors.py). */
import { describe, expect, it } from 'vitest';
import { api, authHeaders, makeRestaurant, makeUser, prisma } from '../helpers.js';

describe('promo codes', () => {
  it('creates a permanent code without dates', async () => {
    const user = await makeUser({ email: 'owner_promo@test.com' });
    const restaurant = await makeRestaurant(user.id);
    const res = await api()
      .post(`/restaurants/${restaurant.id}/promo-codes`)
      .set(await authHeaders(user.email))
      .send({ code: 'WELCOME10', discount_type: 'percent', discount_value: 10 });
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({ code: 'WELCOME10', start_at: null, end_at: null, is_active: true, discount_value: '10.00', usage_count: 0 });
  });

  it('empty end_at clears the expiration', async () => {
    const user = await makeUser({ email: 'owner_promo_update@test.com' });
    const restaurant = await makeRestaurant(user.id);
    const promo = await prisma.restaurantPromoCode.create({
      data: {
        restaurant_id: restaurant.id,
        code: 'FLASH20',
        discount_type: 'percent',
        discount_value: 20,
        start_at: new Date(Date.UTC(2026, 4, 1, 10)),
        end_at: new Date(Date.UTC(2026, 4, 31, 23, 59, 59)),
        is_active: true,
        usage_count: 0,
      },
    });
    const res = await api()
      .put(`/restaurants/${restaurant.id}/promo-codes/${promo.id}`)
      .set(await authHeaders(user.email))
      .send({ end_at: '' });
    expect(res.status).toBe(200);
    expect(res.body.end_at).toBeNull();
    expect((await prisma.restaurantPromoCode.findUniqueOrThrow({ where: { id: promo.id } })).end_at).toBeNull();
  });

  it('order on an unknown restaurant returns 404', async () => {
    const res = await api()
      .post('/restaurants/999999/orders')
      .send({
        type: 'pickup',
        items: [{ product_id: 1, quantity: 1 }],
        customer: { first_name: 'Jane', last_name: 'Doe', phone: '+33600000001', email: 'jane@test.com' },
      });
    expect(res.status).toBe(404);
    expect(res.body.detail).toBe('Restaurant not found');
  });
});
