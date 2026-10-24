/**
 * Chaque route répond sans erreur serveur (tests/test_routes_smoke.py), et le CORS accepte les applications Yumco.
 */
import type { Router } from 'express';
import { beforeEach, describe, expect, it } from 'vitest';
import { env } from '../../src/config/env.js';
import { api, app, authHeaders, makeCategory, makeProduct, makeRestaurant, makeUser } from '../helpers.js';

type Layer = { route?: { path: string; methods: Record<string, boolean> }; handle?: { stack?: Layer[] } };

/** Liste les routes déclarées dans l'application (routeurs imbriqués compris). */
const collectRoutes = () => {
  const routes: { method: string; path: string }[] = [];
  const visit = (stack: Layer[]) => {
    for (const layer of stack) {
      if (layer.route) {
        for (const method of Object.keys(layer.route.methods)) routes.push({ method, path: layer.route.path });
      } else if (layer.handle?.stack) {
        visit(layer.handle.stack);
      }
    }
  };
  visit((app as unknown as { router: Router & { stack: Layer[] } }).router.stack);
  return routes;
};

// 503 : service externe non configuré en test (Stripe, OpenAI).
const ALLOWED = new Set([200, 201, 202, 204, 303, 400, 401, 403, 404, 422, 501, 503]);

describe('routes smoke', () => {
  beforeEach(async () => {
    env.HUBRISE_RESULT_REDIRECT_URI = 'https://dashboard.yumco.fr/hubrise';
    env.REVIEW_FOLLOWUPS_CRON_SECRET = 'secret';
    const admin = await makeUser({ email: 'admin@test.com', isAdmin: true });
    const restaurant = await makeRestaurant(admin.id);
    const category = await makeCategory(restaurant.id);
    await makeProduct(restaurant.id, category.id);
  });

  const routes = collectRoutes();

  it('the application declares all the Python routes', () => {
    // Python : 107 routes dans les routeurs + « / » et « /test-email » ; Node ajoute /subscription (remise en place).
    expect(routes.length).toBe(110);
  });

  it.each(routes.map((route) => [`${route.method.toUpperCase()} ${route.path}`, route] as const))('%s', async (_label, route) => {
    const path = route.path.replace(/:[a-z_]+/g, '1');
    const request = (api() as unknown as Record<string, (path: string) => import('supertest').Test>)[route.method](path).set(await authHeaders('admin@test.com'));
    const res = route.method === 'get' || route.method === 'delete' ? await request : await request.send({});
    expect(ALLOWED.has(res.status), `${route.method.toUpperCase()} ${route.path} → ${res.status} ${JSON.stringify(res.body)}`).toBe(true);
  });
});

describe('cors', () => {
  it('accepts the dashboard origin', async () => {
    const res = await api()
      .options('/restaurants/1/stripe/connect/account')
      .set('Origin', 'https://dashboard.yumco.fr')
      .set('Access-Control-Request-Method', 'POST');
    expect(res.status).toBe(200);
    expect(res.headers['access-control-allow-origin']).toBe('https://dashboard.yumco.fr');
    expect(res.headers['access-control-allow-credentials']).toBe('true');
  });

  it('accepts the local Vite origin', async () => {
    const res = await api().options('/auth/login').set('Origin', 'http://localhost:5173').set('Access-Control-Request-Method', 'POST');
    expect(res.status).toBe(200);
    expect(res.headers['access-control-allow-origin']).toBe('http://localhost:5173');
    expect(res.headers['access-control-allow-credentials']).toBe('true');
  });

  it('refuses an unknown origin', async () => {
    const res = await api().options('/auth/login').set('Origin', 'https://evil.example').set('Access-Control-Request-Method', 'POST');
    expect(res.headers['access-control-allow-origin']).toBeUndefined();
  });
});
