/**
 * Formules « à volonté » (routes/all_you_can_eat.py).
 */
import { Router } from 'express';
import { prisma } from '../../db/prisma.js';
import type { Prisma } from '../../generated/prisma/client.js';
import { notFound } from '../../lib/http-error.js';
import { intParams, validateRequest } from '../../lib/validation.js';
import { restaurantMember } from '../../middleware/auth.js';
import { AllYouCanEatCreate, AllYouCanEatUpdate } from './catalog.schemas.js';
import { toAllYouCanEatResponse } from './catalog.serializers.js';

export const allYouCanEatRouter = Router();

const restaurantParams = intParams('restaurant_id');
const offerParams = intParams('restaurant_id', 'offer_id');

const findOffer = async (restaurantId: number, offerId: number) => {
  const offer = await prisma.allYouCanEat.findFirst({ where: { id: offerId, restaurant_id: restaurantId } });
  if (!offer) throw notFound('Offer not found');
  return offer;
};

allYouCanEatRouter.get('/restaurants/:restaurant_id/all-you-can-eat', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  const offers = await prisma.allYouCanEat.findMany({ where: { restaurant_id: params.restaurant_id }, orderBy: { id: 'asc' } });
  res.json(offers.map(toAllYouCanEatResponse));
});

allYouCanEatRouter.post('/restaurants/:restaurant_id/all-you-can-eat', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: AllYouCanEatCreate });
  const offer = await prisma.allYouCanEat.create({ data: { restaurant_id: params.restaurant_id, name: body.name, price: body.price } });
  res.status(201).json(toAllYouCanEatResponse(offer));
});

allYouCanEatRouter.put('/restaurants/:restaurant_id/all-you-can-eat/:offer_id', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: offerParams, body: AllYouCanEatUpdate });
  const offer = await findOffer(params.restaurant_id, params.offer_id);
  const updated = await prisma.allYouCanEat.update({ where: { id: offer.id }, data: body as Prisma.AllYouCanEatUpdateInput });
  res.json(toAllYouCanEatResponse(updated));
});

allYouCanEatRouter.delete('/restaurants/:restaurant_id/all-you-can-eat/:offer_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: offerParams });
  const offer = await findOffer(params.restaurant_id, params.offer_id);
  await prisma.allYouCanEat.delete({ where: { id: offer.id } });
  res.status(204).end();
});
