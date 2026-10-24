/** Menus avec catégories et options (tests/integration/test_menus.py). */
import { beforeEach, describe, expect, it } from 'vitest';
import { api, authHeaders, makeRestaurant, makeUser } from '../helpers.js';

let ctx: { headers: Record<string, string>; restaurantId: number };

beforeEach(async () => {
  const user = await makeUser({ email: 'owner_menus@test.com' });
  const restaurant = await makeRestaurant(user.id);
  ctx = { headers: await authHeaders(user.email), restaurantId: restaurant.id };
});

const menuPayload = (overrides: Record<string, unknown> = {}) => ({
  name: 'Menu Midi',
  price: '15.50',
  is_available: true,
  available_online: true,
  available_onsite: true,
  categories: [
    {
      name: 'Entrée',
      max_options: 1,
      is_required: true,
      display_order: 0,
      options: [
        { name: 'Salade', additional_price: '0.00', display_order: 0 },
        { name: 'Soupe', additional_price: '1.50', display_order: 1 },
      ],
    },
    {
      name: 'Plat',
      max_options: 1,
      is_required: true,
      display_order: 1,
      options: [
        { name: 'Poulet', additional_price: '0.00', display_order: 0 },
        { name: 'Poisson', additional_price: '2.00', display_order: 1 },
      ],
    },
  ],
  ...overrides,
});

const createMenu = (overrides: Record<string, unknown> = {}) =>
  api().post(`/restaurants/${ctx.restaurantId}/menus`).set(ctx.headers).send(menuPayload(overrides));

describe('menus', () => {
  it('creates a menu with categories', async () => {
    const res = await createMenu();
    expect(res.status).toBe(201);
    expect(res.body.name).toBe('Menu Midi');
    expect(res.body.price).toBe('15.50');
    expect(res.body.categories).toHaveLength(2);
    expect(res.body.categories[0].options).toHaveLength(2);
    expect(res.body.categories[0].options[1].additional_price).toBe('1.50');
  });

  it('lists menus', async () => {
    await createMenu({ name: 'Menu A' });
    await createMenu({ name: 'Menu B' });
    const res = await api().get(`/restaurants/${ctx.restaurantId}/menus`);
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(2);
  });

  it('gets a menu', async () => {
    const created = await createMenu();
    const res = await api().get(`/restaurants/${ctx.restaurantId}/menus/${created.body.id}`);
    expect(res.status).toBe(200);
    expect(res.body.id).toBe(created.body.id);
  });

  it('updates a menu', async () => {
    const created = await createMenu();
    const res = await api()
      .put(`/restaurants/${ctx.restaurantId}/menus/${created.body.id}`)
      .set(ctx.headers)
      .send({ name: 'Menu Soir', price: '22.00', is_available: false });
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ name: 'Menu Soir', price: '22.00', is_available: false });
    // Sans « categories » dans la demande, les catégories existantes sont gardées.
    expect(res.body.categories).toHaveLength(2);
  });

  it('deletes a menu', async () => {
    const created = await createMenu();
    expect((await api().delete(`/restaurants/${ctx.restaurantId}/menus/${created.body.id}`).set(ctx.headers)).status).toBe(204);
    expect((await api().get(`/restaurants/${ctx.restaurantId}/menus/${created.body.id}`)).status).toBe(404);
  });

  it('a menu with an option adds the extra price to the order', async () => {
    const menu = (await createMenu()).body;
    const soupOptionId = menu.categories[0].options[1].id;
    const res = await api()
      .post(`/restaurants/${ctx.restaurantId}/orders`)
      .send({
        type: 'pickup',
        items: [{ menu_id: menu.id, quantity: 1, selected_options: [soupOptionId] }],
        customer: { first_name: 'Jane', last_name: 'Doe', phone: '+33600000010' },
      });
    expect(res.status).toBe(201);
    // 15.50 (menu) + 1.50 (soupe)
    expect(res.body.items_subtotal).toBe(17);
    const option = res.body.items.find((item: { parent_order_item_id: number | null }) => item.parent_order_item_id !== null);
    expect(option).toMatchObject({ name: 'Soupe', unit_price: 1.5, subtotal: 1.5 });
  });

  it('a menu creation with an invalid option is fully cancelled', async () => {
    const res = await api()
      .post(`/restaurants/${ctx.restaurantId}/menus`)
      .set(ctx.headers)
      .send({ name: 'Cassé', price: 10, categories: [{ name: 'C', options: [{}] }] });
    expect(res.status).toBe(400);
    expect(res.body.detail).toBe('Option must have a name or a valid product_id');
    // Correction : en Python, le menu restait créé à moitié.
    expect((await api().get(`/restaurants/${ctx.restaurantId}/menus`)).body).toHaveLength(0);
  });
});
