/**
 * Tables du restaurant (routes/table.py).
 */
import { Router } from 'express';
import { prisma } from '../../db/prisma.js';
import type { Prisma, Table } from '../../generated/prisma/client.js';
import { notFound } from '../../lib/http-error.js';
import { datetime } from '../../lib/serialize.js';
import { intParams, py, validateRequest, z } from '../../lib/validation.js';
import { restaurantMember } from '../../middleware/auth.js';
import { generateTableTicket } from '../orders/receipts.service.js';

const TableCreate = z.object({
  table_number: py.str(),
  number_of_people: py.int(),
  is_available: py.bool().default(true),
  location: py.str().nullable().optional(),
  temporary: py.bool().default(false),
});

const TableUpdate = z.object({
  table_number: py.str().nullable().optional(),
  number_of_people: py.int().nullable().optional(),
  is_available: py.bool().nullable().optional(),
  location: py.str().nullable().optional(),
  temporary: py.bool().nullable().optional(),
});

export const toTableResponse = (table: Table) => ({
  id: table.id,
  restaurant_id: table.restaurant_id,
  table_number: table.table_number,
  number_of_people: table.number_of_people,
  is_available: table.is_available ?? true,
  location: table.location,
  temporary: table.temporary ?? false,
  created_at: datetime(table.created_at!),
});

export const tablesRouter = Router();

const restaurantParams = intParams('restaurant_id');
const tableParams = intParams('restaurant_id', 'table_id');

const findTable = async (restaurantId: number, tableId: number) => {
  const table = await prisma.table.findFirst({ where: { id: tableId, restaurant_id: restaurantId } });
  if (!table) throw notFound('Table not found');
  return table;
};

tablesRouter.get('/restaurants/:restaurant_id/tables', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: restaurantParams });
  const tables = await prisma.table.findMany({ where: { restaurant_id: params.restaurant_id }, orderBy: { id: 'asc' } });
  res.json(tables.map(toTableResponse));
});

tablesRouter.get('/restaurants/:restaurant_id/tables/:table_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: tableParams });
  res.json(toTableResponse(await findTable(params.restaurant_id, params.table_id)));
});

tablesRouter.post('/restaurants/:restaurant_id/tables', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: restaurantParams, body: TableCreate });
  const table = await prisma.table.create({ data: { ...body, location: body.location ?? null, restaurant_id: params.restaurant_id } });
  res.status(201).json(toTableResponse(table));
});

tablesRouter.put('/restaurants/:restaurant_id/tables/:table_id', ...restaurantMember, async (req, res) => {
  const { params, body } = validateRequest(req, { params: tableParams, body: TableUpdate });
  const table = await findTable(params.restaurant_id, params.table_id);
  const updated = await prisma.table.update({ where: { id: table.id }, data: body as Prisma.TableUpdateInput });
  res.json(toTableResponse(updated));
});

tablesRouter.get('/restaurants/:restaurant_id/tables/:table_id/ticket', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: tableParams });
  const table = await findTable(params.restaurant_id, params.table_id);
  const restaurant = await prisma.restaurant.findUniqueOrThrow({ where: { id: params.restaurant_id } });
  const pdf = await generateTableTicket(table, restaurant);
  res
    .status(200)
    .set({ 'Content-Type': 'application/pdf', 'Content-Disposition': `inline; filename=table_${table.table_number}.pdf` })
    .send(pdf);
});

tablesRouter.delete('/restaurants/:restaurant_id/tables/:table_id', ...restaurantMember, async (req, res) => {
  const { params } = validateRequest(req, { params: tableParams });
  const table = await findTable(params.restaurant_id, params.table_id);
  await prisma.table.delete({ where: { id: table.id } });
  res.status(204).end();
});
