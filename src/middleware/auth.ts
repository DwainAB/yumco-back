/**
 * Authentification et permissions (get_current_user, require_admin, check_permission en Python).
 */
import type { NextFunction, Request, Response } from 'express';
import { env } from '../config/env.js';
import { prisma } from '../db/prisma.js';
import type { Prisma } from '../generated/prisma/client.js';
import { forbidden, HttpError, notFound, unauthorized } from '../lib/http-error.js';
import { decodeAccessToken } from '../modules/auth/jwt.js';

export type CurrentUser = Prisma.UserGetPayload<{ include: { roles: true } }>;

declare module 'express-serve-static-core' {
  interface Request {
    user?: CurrentUser;
  }
}

const BEARER = { 'WWW-Authenticate': 'Bearer' };

/** Jeton du header Authorization (OAuth2PasswordBearer) : 401 « Not authenticated » s'il manque. */
const bearerToken = (req: Request): string => {
  const header = req.headers.authorization ?? '';
  const [scheme, ...rest] = header.split(' ');
  const token = rest.join(' ');
  if (!header || scheme.toLowerCase() !== 'bearer') throw unauthorized('Not authenticated', BEARER);
  return token;
};

export const loadUserFromToken = async (token: string): Promise<CurrentUser> => {
  const credentialsError = unauthorized('Could not validate credentials', BEARER);
  const payload = await decodeAccessToken(token);
  if (!payload) throw credentialsError;
  const email = payload.sub;
  if (typeof email !== 'string') throw credentialsError;
  const user = await prisma.user.findFirst({ where: { email }, include: { roles: { orderBy: { id: 'asc' } } } });
  if (!user) throw credentialsError;
  return user;
};

/** Route réservée aux utilisateurs connectés. */
export const authenticate = async (req: Request, _res: Response, next: NextFunction) => {
  req.user = await loadUserFromToken(bearerToken(req));
  next();
};

/** Utilisateur connecté (après `authenticate`). */
export const currentUser = (req: Request): CurrentUser => {
  if (!req.user) throw new HttpError(500, 'authenticate middleware is missing on this route');
  return req.user;
};

/** require_admin : 403 « Admin only ». */
export const requireAdmin = (req: Request, _res: Response, next: NextFunction) => {
  if (!currentUser(req).is_admin) throw forbidden('Admin only');
  next();
};

const MANAGER_ROLES = new Set(['owner', 'manager']);

/** check_permission : admin, ou propriétaire / gérant du restaurant. */
export const checkPermission = async (user: CurrentUser, restaurantId: number) => {
  if (user.is_admin) return;
  const role = await prisma.role.findFirst({ where: { user_id: user.id, restaurant_id: restaurantId } });
  if (!role || !MANAGER_ROLES.has(role.type)) throw forbidden('Not allowed');
};

/** _require_restaurant_owner_or_admin : restaurant non supprimé, puis admin ou propriétaire / gérant. */
export const requireRestaurantOwnerOrAdmin = async (restaurantId: number, user: CurrentUser) => {
  const restaurant = await prisma.restaurant.findFirst({ where: { id: restaurantId, is_deleted: false } });
  if (!restaurant) throw notFound('Restaurant not found');
  if (user.is_admin) return restaurant;
  const role = await prisma.role.findFirst({ where: { restaurant_id: restaurantId, user_id: user.id } });
  if (!role || !MANAGER_ROLES.has(role.type)) throw forbidden('Not allowed');
  return restaurant;
};

/**
 * Correction de sécurité (PLAN_MIGRATION.md §8) : un utilisateur connecté n'accède qu'aux restaurants
 * auxquels il est rattaché, sauf s'il est admin. Désactivable avec STRICT_RESTAURANT_ACCESS=false.
 */
export const requireRestaurantMember = (paramName = 'restaurant_id') =>
  async (req: Request, _res: Response, next: NextFunction) => {
    if (!env.STRICT_RESTAURANT_ACCESS) return next();
    const user = currentUser(req);
    const restaurantId = Number(req.params[paramName]);
    if (user.is_admin || !Number.isInteger(restaurantId)) return next();
    if (!user.roles.some((role) => role.restaurant_id === restaurantId)) throw forbidden('Not allowed');
    next();
  };

/** Raccourci : connecté et rattaché au restaurant de l'URL. */
export const restaurantMember = [authenticate, requireRestaurantMember()];
