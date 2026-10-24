/** Restaurants, catégories, produits (tests/integration/test_restaurant.py). */
import { describe, expect, it } from 'vitest';
import { api, authHeaders, makeCategory, makeProduct, makeRestaurant, makeUser, prisma } from '../helpers.js';

describe('restaurants', () => {
  it('get restaurant (public)', async () => {
    const owner = await makeUser({ email: 'owner_r1@test.com' });
    const restaurant = await makeRestaurant(owner.id, 'Mon Restaurant');
    const res = await api().get(`/restaurants/${restaurant.id}`).set(await authHeaders(owner.email));
    expect(res.status).toBe(200);
    expect(res.body.name).toBe('Mon Restaurant');
  });

  it('get restaurant not found', async () => {
    const res = await api().get('/restaurants/99999').set(await authHeaders('nobody@test.com'));
    expect(res.status).toBe(404);
  });

  it('create restaurant requires admin', async () => {
    const user = await makeUser({ email: 'owner_r2@test.com' });
    const res = await api()
      .post('/restaurants/')
      .set(await authHeaders(user.email))
      .send({
        name: 'Resto',
        email: 'resto@test.com',
        phone: '+33100000002',
        timezone: 'Europe/Paris',
        address: { street: '2 Rue', city: 'Lyon', postal_code: '69001', country: 'FR' },
      });
    expect(res.status).toBe(403);
  });

  it('admin can create restaurant', async () => {
    const admin = await makeUser({ email: 'admin_r@test.com', isAdmin: true });
    const res = await api()
      .post('/restaurants/')
      .set(await authHeaders(admin.email))
      .send({
        name: 'Admin Resto',
        email: 'adminresto@test.com',
        phone: '+33100000003',
        timezone: 'Europe/Paris',
        address: { street: '3 Rue', city: 'Paris', postal_code: '75001', country: 'FR' },
      });
    expect(res.status).toBe(201);
    expect(res.body.name).toBe('Admin Resto');
    // Valeurs par défaut de SQLAlchemy (la base n'en a pas).
    expect(res.body.config).toMatchObject({ accept_orders: false, preparation_time: 30, pickup: true, printer_enabled: false });
    expect(res.body.subscription_interval).toBe('month');
  });

  it('rejects overlapping delivery tier boundaries', async () => {
    const admin = await makeUser({ email: 'admin_delivery_overlap@test.com', isAdmin: true });
    const res = await api()
      .post('/restaurants/')
      .set(await authHeaders(admin.email))
      .send({
        name: 'Overlap Resto',
        email: 'overlapresto@test.com',
        phone: '+33100000013',
        address: { street: '13 Rue', city: 'Paris', postal_code: '75013', country: 'FR' },
        delivery_tiers: [
          { min_km: 0, max_km: 10, price: '4.00', min_order_amount: '0.00' },
          { min_km: 10, max_km: 15, price: '6.00', min_order_amount: '0.00' },
        ],
      });
    expect(res.status).toBe(422);
    expect(JSON.stringify(res.body)).toContain('must not overlap or share a boundary');
  });

  it('allows stacked delivery pricing on the same range', async () => {
    const admin = await makeUser({ email: 'admin_delivery_stack@test.com', isAdmin: true });
    const res = await api()
      .post('/restaurants/')
      .set(await authHeaders(admin.email))
      .send({
        name: 'Stacked Resto',
        email: 'stackedresto@test.com',
        phone: '+33100000014',
        address: { street: '14 Rue', city: 'Paris', postal_code: '75014', country: 'FR' },
        delivery_tiers: [
          { min_km: 0, max_km: 10, price: '4.00', min_order_amount: '0.00' },
          { min_km: 0, max_km: 10, price: '0.00', min_order_amount: '25.00' },
        ],
      });
    expect(res.status).toBe(201);
    expect(res.body.delivery_tiers).toHaveLength(2);
    expect(res.body.delivery_tiers[0].price).toBe('4.00');
  });

  it('update restaurant', async () => {
    const owner = await makeUser({ email: 'owner_r3@test.com' });
    const restaurant = await makeRestaurant(owner.id);
    const res = await api().put(`/restaurants/${restaurant.id}`).set(await authHeaders(owner.email)).send({ name: 'Nouveau Nom' });
    expect(res.status).toBe(200);
    expect(res.body.name).toBe('Nouveau Nom');
  });

  it('create category and product (form)', async () => {
    const owner = await makeUser({ email: 'owner_r4@test.com' });
    const restaurant = await makeRestaurant(owner.id);
    const headers = await authHeaders(owner.email);

    const category = await api().post(`/restaurants/${restaurant.id}/categories`).set(headers).send({ name: 'Pizzas' });
    expect(category.status).toBe(201);

    const res = await api()
      .post(`/restaurants/${restaurant.id}/products`)
      .set(headers)
      .field('name', 'Margherita')
      .field('price', '11.50')
      .field('category_id', String(category.body.id))
      .field('group', 'main')
      .field('is_available', 'true')
      .field('available_online', 'true')
      .field('available_onsite', 'true');
    expect(res.status).toBe(201);
    expect(res.body.name).toBe('Margherita');
    expect(res.body.price).toBe('11.50');
  });

  it('list products', async () => {
    const owner = await makeUser({ email: 'owner_r5@test.com' });
    const restaurant = await makeRestaurant(owner.id);
    const category = await makeCategory(restaurant.id);
    await makeProduct(restaurant.id, category.id, 'Burger', 12.5);
    await makeProduct(restaurant.id, category.id, 'Frites', 4.0);
    const res = await api().get(`/restaurants/${restaurant.id}/products`).set(await authHeaders(owner.email));
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(2);
  });

  it('delete product (soft)', async () => {
    const owner = await makeUser({ email: 'owner_r6@test.com' });
    const restaurant = await makeRestaurant(owner.id);
    const category = await makeCategory(restaurant.id);
    const product = await makeProduct(restaurant.id, category.id);
    const headers = await authHeaders(owner.email);

    expect((await api().delete(`/restaurants/${restaurant.id}/products/${product.id}`).set(headers)).status).toBe(204);
    const res = await api().get(`/restaurants/${restaurant.id}/products`).set(headers);
    expect(res.body.every((p: { id: number }) => p.id !== product.id)).toBe(true);
  });

  it('admin can hard delete a restaurant with delivery tiers', async () => {
    const admin = await makeUser({ email: 'admin_delete_restaurant@test.com', isAdmin: true });
    const owner = await makeUser({ email: 'owner_delete_restaurant@test.com' });
    const restaurant = await makeRestaurant(owner.id, 'Delete Me');
    await prisma.deliveryTier.createMany({
      data: [
        { restaurant_id: restaurant.id, min_km: 0, max_km: 5, price: '2.50', min_order_amount: '0.00' },
        { restaurant_id: restaurant.id, min_km: 5, max_km: 10, price: '4.50', min_order_amount: '0.00' },
      ],
    });

    const res = await api().delete(`/admin/restaurants/${restaurant.id}`).set(await authHeaders(admin.email));
    expect(res.status).toBe(204);
    expect(await prisma.restaurant.findUnique({ where: { id: restaurant.id } })).toBeNull();
    expect(await prisma.deliveryTier.count({ where: { restaurant_id: restaurant.id } })).toBe(0);
  });
});
