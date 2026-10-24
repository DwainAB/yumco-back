/**
 * Routes /restaurants (routes/restaurant.py).
 */
import { Router } from 'express';
import { env } from '../../config/env.js';
import { prisma } from '../../db/prisma.js';
import type { Restaurant } from '../../generated/prisma/client.js';
import { badRequest, forbidden, notFound } from '../../lib/http-error.js';
import { intParams, validateRequest } from '../../lib/validation.js';
import { authenticate, currentUser, requireRestaurantOwnerOrAdmin, restaurantMember, type CurrentUser } from '../../middleware/auth.js';
import { toUserResponse } from '../auth/users.serializers.js';
import { getDeliveryCities } from '../geo/geo.service.js';
import { getSubscriptionUsage } from '../subscriptions/subscriptions.service.js';
import { RestaurantCreate, RestaurantUpdate } from './restaurants.schemas.js';
import { toRestaurantResponse } from './restaurants.serializers.js';
import { createRestaurant, getRestaurant, getRestaurantsByUser, softDeleteRestaurant, updateRestaurant } from './restaurants.service.js';

export const restaurantsRouter = Router();

const restaurantIdParam = intParams('restaurant_id');

restaurantsRouter.get('/restaurants/:restaurant_id/users', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantIdParam });
  const users = await prisma.user.findMany({
    where: { roles: { some: { restaurant_id: params.restaurant_id } } },
    include: { roles: { orderBy: { id: 'asc' } } },
    orderBy: { id: 'asc' },
  });
  res.json(users.map(toUserResponse));
});

restaurantsRouter.get('/restaurants', authenticate, async (req, res) => {
  const restaurants = await getRestaurantsByUser(currentUser(req).id);
  res.json(restaurants.map(toRestaurantResponse));
});

restaurantsRouter.get('/restaurants/:restaurant_id', async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantIdParam });
  const restaurant = await getRestaurant(params.restaurant_id);
  if (!restaurant) throw notFound('Restaurant not found');
  res.json(toRestaurantResponse(restaurant));
});

restaurantsRouter.post('/restaurants', authenticate, async (req, res) => {
  const { body } = validateRequest(req, { body: RestaurantCreate });
  if (!currentUser(req).is_admin) throw forbidden('Admin only');
  res.status(201).json(toRestaurantResponse(await createRestaurant(body)));
});

/** Champs d'abonnement, de quotas et de paiement : seul un admin peut les changer (correction de sécurité). */
const ADMIN_ONLY_FIELDS = [
  'stripe_id',
  'subscription_plan',
  'subscription_status',
  'ai_monthly_quota',
  'ai_usage_count',
  'ai_monthly_token_quota',
  'ai_token_usage_count',
  'ai_cycle_started_at',
] as const;

const sameValue = (a: unknown, b: unknown) =>
  a instanceof Date || b instanceof Date ? (a as Date | null)?.getTime() === (b as Date | null)?.getTime() : a === b;

/** L'application renvoie le restaurant complet : une valeur inchangée est ignorée, une valeur modifiée est refusée. */
const guardAdminOnlyFields = (data: RestaurantUpdate, restaurant: Restaurant, user: CurrentUser): RestaurantUpdate => {
  if (!env.STRICT_RESTAURANT_ACCESS || user.is_admin) return data;
  const guarded: Record<string, unknown> = { ...data };
  for (const field of ADMIN_ONLY_FIELDS) {
    if (guarded[field] === undefined) continue;
    if (!sameValue(guarded[field], restaurant[field])) throw forbidden('Not allowed');
    delete guarded[field];
  }
  return guarded as RestaurantUpdate;
};

restaurantsRouter.put('/restaurants/:restaurant_id', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantIdParam, body: RestaurantUpdate });
  const restaurant = await getRestaurant(params.restaurant_id);
  if (!restaurant) throw notFound('Restaurant not found');
  const data = guardAdminOnlyFields(body, restaurant, currentUser(req));
  res.json(toRestaurantResponse(await updateRestaurant(restaurant.id, restaurant.address_id, data)));
});

restaurantsRouter.get('/restaurants/:restaurant_id/delivery-cities', async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantIdParam });
  const restaurant = await getRestaurant(params.restaurant_id);
  if (!restaurant) throw notFound('Restaurant not found');
  if (!restaurant.address) throw badRequest('Restaurant has no address');
  if (!restaurant.config || restaurant.config.max_delivery_km === null) throw badRequest('max_delivery_km not configured');

  const { street, city, postal_code, country } = restaurant.address;
  res.json(await getDeliveryCities({ street, city, postal_code, country }, restaurant.config.max_delivery_km));
});

/**
 * Remise en place de la route supprimée le 01/05/2026 (commit 9569317) : le dashboard l'appelle toujours.
 * Lecture seule, réservée au propriétaire, au gérant ou à un admin, comme avant sa suppression.
 */
restaurantsRouter.get('/restaurants/:restaurant_id/subscription', authenticate, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantIdParam });
  const restaurant = await requireRestaurantOwnerOrAdmin(params.restaurant_id, currentUser(req));
  res.json(await getSubscriptionUsage(restaurant));
});

restaurantsRouter.delete('/restaurants/:restaurant_id', authenticate, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantIdParam });
  if (!currentUser(req).is_admin) throw forbidden('Admin only');
  const restaurant = await getRestaurant(params.restaurant_id);
  if (!restaurant) throw notFound('Restaurant not found');
  await softDeleteRestaurant(restaurant.id);
  res.status(204).end();
});
