/** Authentification (tests/integration/test_auth.py). */
import { describe, expect, it } from 'vitest';
import { api, authHeaders, makeRestaurant, makeUser } from '../helpers.js';

describe('auth', () => {
  it('login success', async () => {
    await makeUser({ email: 'login@test.com', password: 'password123' });
    const res = await api().post('/auth/login').send({ email: 'login@test.com', password: 'password123' });
    expect(res.status).toBe(200);
    expect(res.body.access_token).toBeDefined();
    expect(res.body.token_type).toBe('bearer');
  });

  it('login wrong password', async () => {
    await makeUser({ email: 'wrong@test.com', password: 'correct' });
    const res = await api().post('/auth/login').send({ email: 'wrong@test.com', password: 'bad' });
    expect(res.status).toBe(401);
    expect(res.body.detail).toBe('Invalid email or password');
  });

  it('get me', async () => {
    await makeUser({ email: 'me@test.com' });
    const res = await api().get('/auth/me').set(await authHeaders('me@test.com'));
    expect(res.status).toBe(200);
    expect(res.body.email).toBe('me@test.com');
  });

  it('get me without token', async () => {
    const res = await api().get('/auth/me');
    expect(res.status).toBe(401);
    expect(res.body.detail).toBe('Not authenticated');
    expect(res.headers['www-authenticate']).toBe('Bearer');
  });

  it('register staff as admin', async () => {
    const admin = await makeUser({ email: 'admin@test.com', isAdmin: true });
    const restaurant = await makeRestaurant(admin.id);
    const res = await api()
      .post('/auth/register')
      .set(await authHeaders('admin@test.com'))
      .send({
        email: 'staff@test.com',
        password: 'password123',
        first_name: 'Jean',
        last_name: 'Dupont',
        phone: '+33600000099',
        restaurant_id: restaurant.id,
        role: 'manager',
      });
    expect(res.status).toBe(201);
    expect(res.body.email).toBe('staff@test.com');
    expect(res.body.roles).toEqual([{ restaurant_id: restaurant.id, type: 'manager' }]);
  });

  it('register duplicate email rejected', async () => {
    const admin = await makeUser({ email: 'admin2@test.com', isAdmin: true });
    const restaurant = await makeRestaurant(admin.id);
    await makeUser({ email: 'dup@test.com' });
    const res = await api()
      .post('/auth/register')
      .set(await authHeaders('admin2@test.com'))
      .send({
        email: 'dup@test.com',
        password: 'password123',
        first_name: 'Jean',
        last_name: 'Dupont',
        phone: '+33600000088',
        restaurant_id: restaurant.id,
        role: 'manager',
      });
    expect(res.status).toBe(400);
  });
});
