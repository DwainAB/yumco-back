/**
 * Annonces affichées sur la plateforme (routes/announcement.py, announcement_service.py, schemas/announcement.py).
 */
import { Router } from 'express';
import { prisma } from '../../db/prisma.js';
import type { Prisma, RestaurantAnnouncement } from '../../generated/prisma/client.js';
import { notFound } from '../../lib/http-error.js';
import { datetime, datetimeOrNull } from '../../lib/serialize.js';
import { afterFields, intParams, py, valueError, validateRequest, z } from '../../lib/validation.js';
import { restaurantMember } from '../../middleware/auth.js';

const TYPES = ['info', 'promotion', 'new_menu', 'exceptional_closure', 'warning'];
const SCOPES = ['home', 'cart', 'reservation', 'all'];

const oneOf = (field: string, allowed: string[]) =>
  py.str().transform((value, ctx) => {
    const normalized = value.trim().toLowerCase();
    if (!allowed.includes(normalized)) {
      valueError(ctx, `${field} must be one of: ${[...allowed].sort().join(', ')}`, [], value);
      return z.NEVER;
    }
    return normalized;
  });

const requiredText = (field: string) =>
  py.str().transform((value, ctx) => {
    const normalized = value.trim();
    if (!normalized) {
      valueError(ctx, `${field} is required`, [], value);
      return z.NEVER;
    }
    return normalized;
  });

const AnnouncementCreate = z
  .object({
    type: oneOf('type', TYPES),
    title: requiredText('title'),
    message: requiredText('message'),
    display_scope: oneOf('display_scope', SCOPES).default('all'),
    priority: py.int().default(0),
    start_at: py.datetime().nullable().optional(),
    end_at: py.datetime().nullable().optional(),
    is_active: py.bool().default(true),
  })
  .superRefine((data, ctx) => {
    if (data.end_at && data.start_at && data.end_at.getTime() <= data.start_at.getTime()) {
      valueError(ctx, 'end_at must be after start_at', ['end_at'], data.end_at.toISOString());
    }
  }, afterFields('start_at', 'end_at'));

const AnnouncementUpdate = z.object({
  type: oneOf('type', TYPES).nullable().optional(),
  title: requiredText('title').nullable().optional(),
  message: requiredText('message').nullable().optional(),
  display_scope: oneOf('display_scope', SCOPES).nullable().optional(),
  priority: py.int().nullable().optional(),
  start_at: py.datetime().nullable().optional(),
  end_at: py.datetime().nullable().optional(),
  is_active: py.bool().nullable().optional(),
});

const toAnnouncementResponse = (announcement: RestaurantAnnouncement) => ({
  type: announcement.type,
  title: announcement.title,
  message: announcement.message,
  display_scope: announcement.display_scope,
  priority: announcement.priority,
  start_at: datetimeOrNull(announcement.start_at),
  end_at: datetimeOrNull(announcement.end_at),
  is_active: announcement.is_active,
  id: announcement.id,
  restaurant_id: announcement.restaurant_id,
  created_at: datetime(announcement.created_at!),
});

const byPriority = [{ priority: 'desc' }, { created_at: { sort: 'desc', nulls: 'first' } }, { id: 'desc' }] satisfies Prisma.RestaurantAnnouncementOrderByWithRelationInput[];

const getRestaurantOr404 = async (restaurantId: number) => {
  const restaurant = await prisma.restaurant.findFirst({ where: { id: restaurantId, is_deleted: false } });
  if (!restaurant) throw notFound('Restaurant not found');
  return restaurant;
};

const findAnnouncement = async (restaurantId: number, announcementId: number) => {
  const announcement = await prisma.restaurantAnnouncement.findFirst({ where: { restaurant_id: restaurantId, id: announcementId } });
  if (!announcement) throw notFound('Announcement not found');
  return announcement;
};

export const announcementsRouter = Router();

const restaurantParams = intParams('restaurant_id');
const announcementParams = intParams('restaurant_id', 'announcement_id');

announcementsRouter.get('/restaurants/:restaurant_id/announcements', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  await getRestaurantOr404(params.restaurant_id);
  const announcements = await prisma.restaurantAnnouncement.findMany({ where: { restaurant_id: params.restaurant_id }, orderBy: byPriority });
  res.json(announcements.map(toAnnouncementResponse));
});

/** Annonces en cours, pour la plateforme publique. */
announcementsRouter.get('/restaurants/:restaurant_id/announcements/active', async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  await getRestaurantOr404(params.restaurant_id);
  const now = new Date();
  const announcements = await prisma.restaurantAnnouncement.findMany({
    where: {
      restaurant_id: params.restaurant_id,
      is_active: true,
      AND: [{ OR: [{ start_at: null }, { start_at: { lte: now } }] }, { OR: [{ end_at: null }, { end_at: { gte: now } }] }],
    },
    orderBy: byPriority,
  });
  res.json(announcements.map(toAnnouncementResponse));
});

announcementsRouter.post('/restaurants/:restaurant_id/announcements', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: AnnouncementCreate });
  await getRestaurantOr404(params.restaurant_id);
  const announcement = await prisma.restaurantAnnouncement.create({
    data: { ...body, start_at: body.start_at ?? null, end_at: body.end_at ?? null, restaurant_id: params.restaurant_id },
  });
  res.status(201).json(toAnnouncementResponse(announcement));
});

announcementsRouter.put('/restaurants/:restaurant_id/announcements/:announcement_id', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: announcementParams, body: AnnouncementUpdate });
  await getRestaurantOr404(params.restaurant_id);
  const announcement = await findAnnouncement(params.restaurant_id, params.announcement_id);
  const updated = await prisma.restaurantAnnouncement.update({ where: { id: announcement.id }, data: body as Prisma.RestaurantAnnouncementUpdateInput });
  res.json(toAnnouncementResponse(updated));
});

announcementsRouter.delete('/restaurants/:restaurant_id/announcements/:announcement_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: announcementParams });
  await getRestaurantOr404(params.restaurant_id);
  const announcement = await findAnnouncement(params.restaurant_id, params.announcement_id);
  await prisma.restaurantAnnouncement.delete({ where: { id: announcement.id } });
  res.status(204).end();
});
