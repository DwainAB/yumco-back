/** Réservations (tests/integration/test_reservations.py). */
import { beforeEach, describe, expect, it } from 'vitest';
import { api, authHeaders, makeRestaurant, makeUser } from '../helpers.js';
import { notifyNewReservation } from '../../src/modules/notifications/push.service.js';
import { flushBackgroundTasks } from '../../src/lib/background.js';

let ctx: { headers: Record<string, string>; restaurantId: number };

beforeEach(async () => {
  const user = await makeUser({ email: 'owner_res@test.com' });
  const restaurant = await makeRestaurant(user.id);
  ctx = { headers: await authHeaders(user.email), restaurantId: restaurant.id };
});

const payload = (overrides: Record<string, unknown> = {}) => ({
  full_name: 'Jean Dupont',
  phone: '+33600000001',
  email: 'jean@test.com',
  number_of_people: 4,
  reservation_date: '2026-06-15',
  reservation_time: '19:30:00',
  comment: 'Table fenêtre',
  ...overrides,
});

const create = (overrides: Record<string, unknown> = {}) => api().post(`/restaurants/${ctx.restaurantId}/reservations`).send(payload(overrides));

describe('reservations', () => {
  it('creates a reservation and notifies the team', async () => {
    const res = await create();
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({ full_name: 'Jean Dupont', number_of_people: 4, status: 'pending', reservation_date: '2026-06-15', reservation_time: '19:30:00' });
    await flushBackgroundTasks();
    expect(notifyNewReservation).toHaveBeenCalledWith(ctx.restaurantId, 'Jean Dupont', 4, '2026-06-15', '19:30');
  });

  it('lists reservations', async () => {
    await create();
    await create({ full_name: 'Marie Martin', phone: '+33600000002' });
    const res = await api().get(`/restaurants/${ctx.restaurantId}/reservations`).set(ctx.headers);
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(2);
  });

  it('gets a reservation', async () => {
    const created = await create();
    const res = await api().get(`/restaurants/${ctx.restaurantId}/reservations/${created.body.id}`).set(ctx.headers);
    expect(res.status).toBe(200);
    expect(res.body.id).toBe(created.body.id);
  });

  it('updates the status (PATCH)', async () => {
    const created = await create();
    const res = await api().patch(`/restaurants/${ctx.restaurantId}/reservations/${created.body.id}`).set(ctx.headers).send({ status: 'confirmed' });
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('confirmed');
  });

  it('updates the details (PUT)', async () => {
    const created = await create();
    const res = await api()
      .put(`/restaurants/${ctx.restaurantId}/reservations/${created.body.id}`)
      .set(ctx.headers)
      .send({ number_of_people: 6, comment: 'Anniversaire' });
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ number_of_people: 6, comment: 'Anniversaire' });
  });

  it('deletes a reservation', async () => {
    const created = await create();
    expect((await api().delete(`/restaurants/${ctx.restaurantId}/reservations/${created.body.id}`).set(ctx.headers)).status).toBe(204);
    expect((await api().get(`/restaurants/${ctx.restaurantId}/reservations/${created.body.id}`).set(ctx.headers)).status).toBe(404);
  });

  it('unknown reservation', async () => {
    const res = await api().get(`/restaurants/${ctx.restaurantId}/reservations/99999`).set(ctx.headers);
    expect(res.status).toBe(404);
    expect(res.body.detail).toBe('Reservation not found');
  });
});
