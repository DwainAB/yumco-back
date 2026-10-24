/**
 * Clients du restaurant (routes/customer.py).
 */
import { Router } from 'express';
import { prisma } from '../../db/prisma.js';
import type { Customer, Prisma } from '../../generated/prisma/client.js';
import { notFound } from '../../lib/http-error.js';
import { datetime, datetimeOrNull } from '../../lib/serialize.js';
import { intParams, py, validateRequest, z } from '../../lib/validation.js';
import { restaurantMember } from '../../middleware/auth.js';

export const CustomerCreate = z.object({
  first_name: py.str(),
  last_name: py.str(),
  email: py.email().nullable().optional(),
  phone: py.str().nullable().optional(),
});
export type CustomerCreate = z.output<typeof CustomerCreate>;

const CustomerUpdate = z.object({
  first_name: py.str().nullable().optional(),
  last_name: py.str().nullable().optional(),
  email: py.email().nullable().optional(),
  phone: py.str().nullable().optional(),
});

export const toCustomerResponse = (customer: Customer) => ({
  id: customer.id,
  restaurant_id: customer.restaurant_id,
  first_name: customer.first_name,
  last_name: customer.last_name,
  email: customer.email,
  phone: customer.phone,
  created_at: datetime(customer.created_at!),
  updated_at: datetimeOrNull(customer.updated_at),
});

export const customersRouter = Router();

const restaurantParams = intParams('restaurant_id');
const customerParams = intParams('restaurant_id', 'customer_id');

const findCustomer = async (restaurantId: number, customerId: number) => {
  const customer = await prisma.customer.findFirst({ where: { id: customerId, restaurant_id: restaurantId } });
  if (!customer) throw notFound('Customer not found');
  return customer;
};

customersRouter.get('/restaurants/:restaurant_id/customers', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  const customers = await prisma.customer.findMany({ where: { restaurant_id: params.restaurant_id }, orderBy: { id: 'asc' } });
  res.json(customers.map(toCustomerResponse));
});

customersRouter.get('/restaurants/:restaurant_id/customers/:customer_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: customerParams });
  res.json(toCustomerResponse(await findCustomer(params.restaurant_id, params.customer_id)));
});

customersRouter.put('/restaurants/:restaurant_id/customers/:customer_id', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: customerParams, body: CustomerUpdate });
  const customer = await findCustomer(params.restaurant_id, params.customer_id);
  res.json(toCustomerResponse(await prisma.customer.update({ where: { id: customer.id }, data: body as Prisma.CustomerUpdateInput })));
});

customersRouter.delete('/restaurants/:restaurant_id/customers/:customer_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: customerParams });
  const customer = await findCustomer(params.restaurant_id, params.customer_id);
  await prisma.customer.delete({ where: { id: customer.id } });
  res.status(204).end();
});
