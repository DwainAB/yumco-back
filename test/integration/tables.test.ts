/** Tables (tests/integration/test_tables.py). */
import { beforeEach, describe, expect, it } from 'vitest';
import { api, authHeaders, makeCategory, makeProduct, makeRestaurant, makeUser } from '../helpers.js';

let ctx: { headers: Record<string, string>; restaurantId: number };

beforeEach(async () => {
  const user = await makeUser({ email: 'owner_tables@test.com' });
  const restaurant = await makeRestaurant(user.id);
  ctx = { headers: await authHeaders(user.email), restaurantId: restaurant.id };
});

const createTable = (body: Record<string, unknown>) => api().post(`/restaurants/${ctx.restaurantId}/tables`).set(ctx.headers).send(body);

describe('tables', () => {
  it('creates and lists tables', async () => {
    const res = await createTable({ table_number: 'T1', number_of_people: 4, is_available: true, location: 'salle principale' });
    expect(res.status).toBe(201);
    expect(res.body.table_number).toBe('T1');
    const list = await api().get(`/restaurants/${ctx.restaurantId}/tables`).set(ctx.headers);
    expect(list.status).toBe(200);
    expect(list.body).toHaveLength(1);
  });

  it('updates a table', async () => {
    const created = await createTable({ table_number: 'T2', number_of_people: 2 });
    const res = await api().put(`/restaurants/${ctx.restaurantId}/tables/${created.body.id}`).set(ctx.headers).send({ number_of_people: 6, is_available: false });
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ number_of_people: 6, is_available: false });
  });

  it('deletes a table', async () => {
    const created = await createTable({ table_number: 'T3', number_of_people: 2 });
    expect((await api().delete(`/restaurants/${ctx.restaurantId}/tables/${created.body.id}`).set(ctx.headers)).status).toBe(204);
    expect((await api().get(`/restaurants/${ctx.restaurantId}/tables/${created.body.id}`).set(ctx.headers)).status).toBe(404);
  });

  it('a completed onsite order frees its table', async () => {
    const table = await createTable({ table_number: 'T4', number_of_people: 4, is_available: false });
    const category = await makeCategory(ctx.restaurantId);
    const product = await makeProduct(ctx.restaurantId, category.id);
    const order = await api()
      .post(`/restaurants/${ctx.restaurantId}/orders`)
      .send({ type: 'onsite', table_id: table.body.id, items: [{ product_id: product.id, quantity: 1 }] });
    expect(order.status).toBe(201);
    await api().post(`/restaurants/${ctx.restaurantId}/orders/${order.body.id}/status`).set(ctx.headers).send({ status: 'completed' });
    const check = await api().get(`/restaurants/${ctx.restaurantId}/tables/${table.body.id}`).set(ctx.headers);
    expect(check.body.is_available).toBe(true);
  });

  it('table ticket is a pdf', async () => {
    const table = await createTable({ table_number: '7', number_of_people: 2, location: 'Terrasse' });
    const res = await api()
      .get(`/restaurants/${ctx.restaurantId}/tables/${table.body.id}/ticket`)
      .set(ctx.headers)
      .buffer(true)
      .parse((response, callback) => {
        const chunks: Buffer[] = [];
        response.on('data', (chunk: Buffer) => chunks.push(chunk));
        response.on('end', () => callback(null, Buffer.concat(chunks)));
      });
    expect(res.status).toBe(200);
    expect(res.headers['content-disposition']).toBe('inline; filename=table_7.pdf');
    expect((res.body as Buffer).subarray(0, 4).toString()).toBe('%PDF');
  });
});
