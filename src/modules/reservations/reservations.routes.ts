/**
 * Réservations (routes/reservation.py).
 */
import { Router, type Request, type Response } from 'express';
import { prisma } from '../../db/prisma.js';
import type { Prisma, Reservation } from '../../generated/prisma/client.js';
import { addBackgroundTask } from '../../lib/background.js';
import { notFound } from '../../lib/http-error.js';
import { date, datetime, time } from '../../lib/serialize.js';
import { intParams, py, validateRequest, z } from '../../lib/validation.js';
import { restaurantMember } from '../../middleware/auth.js';
import { notifyNewReservation } from '../notifications/push.service.js';

const ReservationCreate = z.object({
  full_name: py.str(),
  email: py.email().nullable().optional(),
  phone: py.str(),
  number_of_people: py.int(),
  reservation_date: py.date(),
  reservation_time: py.time(),
  comment: py.str().nullable().optional(),
});

const ReservationUpdate = z.object({
  full_name: py.str().nullable().optional(),
  email: py.email().nullable().optional(),
  phone: py.str().nullable().optional(),
  number_of_people: py.int().nullable().optional(),
  reservation_date: py.date().nullable().optional(),
  reservation_time: py.time().nullable().optional(),
  comment: py.str().nullable().optional(),
  status: py.str().nullable().optional(),
});

const toReservationResponse = (reservation: Reservation) => ({
  id: reservation.id,
  restaurant_id: reservation.restaurant_id,
  full_name: reservation.full_name,
  email: reservation.email,
  phone: reservation.phone,
  number_of_people: reservation.number_of_people,
  reservation_date: date(reservation.reservation_date),
  reservation_time: time(reservation.reservation_time),
  comment: reservation.comment,
  status: reservation.status,
  created_at: datetime(reservation.created_at!),
});

export const reservationsRouter = Router();

const restaurantParams = intParams('restaurant_id');
const reservationParams = intParams('restaurant_id', 'reservation_id');

const findReservation = async (restaurantId: number, reservationId: number) => {
  const reservation = await prisma.reservation.findFirst({ where: { id: reservationId, restaurant_id: restaurantId } });
  if (!reservation) throw notFound('Reservation not found');
  return reservation;
};

reservationsRouter.get('/restaurants/:restaurant_id/reservations', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  const reservations = await prisma.reservation.findMany({ where: { restaurant_id: params.restaurant_id }, orderBy: { id: 'asc' } });
  res.json(reservations.map(toReservationResponse));
});

reservationsRouter.get('/restaurants/:restaurant_id/reservations/:reservation_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: reservationParams });
  res.json(toReservationResponse(await findReservation(params.restaurant_id, params.reservation_id)));
});

/** Réservation en ligne (publique) : l'équipe reçoit une notification. */
reservationsRouter.post('/restaurants/:restaurant_id/reservations', async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: ReservationCreate });
  const reservation = await prisma.reservation.create({
    data: { ...body, email: body.email ?? null, comment: body.comment ?? null, status: 'pending', restaurant_id: params.restaurant_id },
  });
  addBackgroundTask(res, 'notify_new_reservation', () =>
    notifyNewReservation(
      params.restaurant_id,
      reservation.full_name,
      reservation.number_of_people,
      date(reservation.reservation_date),
      time(reservation.reservation_time).slice(0, 5),
    ),
  );
  res.status(201).json(toReservationResponse(reservation));
});

const updateReservation = async (req: Request, res: Response) => {
  const { params, body } = validateRequest(req, { params: reservationParams, body: ReservationUpdate });
  const reservation = await findReservation(params.restaurant_id, params.reservation_id);
  const updated = await prisma.reservation.update({ where: { id: reservation.id }, data: body as Prisma.ReservationUpdateInput });
  res.json(toReservationResponse(updated));
};

reservationsRouter.put('/restaurants/:restaurant_id/reservations/:reservation_id', ...restaurantMember, updateReservation);
reservationsRouter.patch('/restaurants/:restaurant_id/reservations/:reservation_id', ...restaurantMember, updateReservation);

reservationsRouter.delete('/restaurants/:restaurant_id/reservations/:reservation_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: reservationParams });
  const reservation = await findReservation(params.restaurant_id, params.reservation_id);
  await prisma.reservation.delete({ where: { id: reservation.id } });
  res.status(204).end();
});
