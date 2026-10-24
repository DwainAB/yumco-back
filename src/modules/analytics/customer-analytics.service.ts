/**
 * Statistiques clients (customer_analytics_service.py).
 */
import type { DateTime } from 'luxon';
import { prisma } from '../../db/prisma.js';
import { pyRound } from '../../lib/python.js';
import { localDatetime } from '../../lib/serialize.js';
import { nowIn, periodBounds, toZone, zoneOf } from '../../lib/time.js';
import { MONTH_LABELS, percentageChange, toFloat } from './analytics.helpers.js';

/** Un client est reconnu par son e-mail, sinon par les chiffres de son téléphone, sinon par sa fiche. */
const identityOf = (email: string | null, phone: string | null, customerId: number) =>
  email?.trim().toLowerCase() || (phone ?? '').replace(/\D/g, '') || `customer:${customerId}`;

interface CustomerStats {
  identity: string;
  first_name: string;
  last_name: string;
  orders_count: number;
  total_spent: number;
  last_order_at: DateTime;
  first_order_at: DateTime;
}

export const getCustomerAnalytics = async (restaurantId: number) => {
  const restaurant = await prisma.restaurant.findUnique({ where: { id: restaurantId } });
  if (!restaurant) return null;

  const zone = zoneOf(restaurant.timezone);
  const bounds = periodBounds(nowIn(zone));

  const rows = await prisma.$queryRaw<
    { customer_id: number; first_name: string; last_name: string; email: string | null; phone: string | null; amount_total: unknown; order_created_at: Date }[]
  >`
    SELECT c.id AS customer_id, c.first_name, c.last_name, c.email, c.phone, o.amount_total, o.created_at AS order_created_at
    FROM customers c JOIN orders o ON o.customer_id = c.id
    WHERE c.restaurant_id = ${restaurantId} AND o.restaurant_id = ${restaurantId} AND o.status != 'cancelled'
    ORDER BY o.created_at ASC`;

  const customers = new Map<string, CustomerStats>();
  const newCustomersByMonth = new Map<string, { year: number; month: number; count: number }>();

  for (const row of rows) {
    const identity = identityOf(row.email, row.phone, row.customer_id);
    const createdAtLocal = toZone(row.order_created_at, zone);
    let customer = customers.get(identity);
    if (!customer) {
      customer = {
        identity,
        first_name: row.first_name,
        last_name: row.last_name,
        orders_count: 0,
        total_spent: 0,
        last_order_at: createdAtLocal,
        first_order_at: createdAtLocal,
      };
      customers.set(identity, customer);
      const key = `${createdAtLocal.year}-${String(createdAtLocal.month).padStart(2, '0')}`;
      const bucket = newCustomersByMonth.get(key) ?? { year: createdAtLocal.year, month: createdAtLocal.month, count: 0 };
      bucket.count += 1;
      newCustomersByMonth.set(key, bucket);
    }
    customer.orders_count += 1;
    customer.total_spent += toFloat(row.amount_total);
    if (createdAtLocal > customer.last_order_at) {
      customer.last_order_at = createdAtLocal;
      customer.first_name = row.first_name;
      customer.last_name = row.last_name;
    }
  }

  const all = [...customers.values()];
  const loyalCount = all.filter((customer) => customer.orders_count >= 2).length;
  const totalCount = all.length;
  const monthStart = bounds.month_start_utc.getTime();
  const previousMonthTotal = all.filter((customer) => customer.first_order_at.toMillis() < monthStart).length;

  const topCustomers = [...all]
    .sort((a, b) => b.orders_count - a.orders_count || b.total_spent - a.total_spent || b.last_order_at.toMillis() - a.last_order_at.toMillis())
    .slice(0, 3);

  const years = new Map<number, { month: string; count: number; change_percentage_vs_previous_month: number | null }[]>();
  let previousCount: number | null = null;
  for (const [, bucket] of [...newCustomersByMonth].sort(([a], [b]) => a.localeCompare(b))) {
    const months = years.get(bucket.year) ?? [];
    months.push({
      month: MONTH_LABELS[bucket.month],
      count: bucket.count,
      change_percentage_vs_previous_month: previousCount !== null ? percentageChange(bucket.count, previousCount) : null,
    });
    years.set(bucket.year, months);
    previousCount = bucket.count;
  }

  return {
    total_customers: { total: totalCount, change_percentage_vs_previous_month: percentageChange(totalCount, previousMonthTotal) },
    loyal_customers: { total: loyalCount, percentage_of_total_customers: totalCount ? pyRound((loyalCount / totalCount) * 100, 2) : 0 },
    top_customers: topCustomers.map((customer) => ({
      identity: customer.identity,
      first_name: customer.first_name,
      last_name: customer.last_name,
      orders_count: customer.orders_count,
      total_spent: pyRound(customer.total_spent, 2),
      last_order_at: localDatetime(customer.last_order_at),
    })),
    new_customers_breakdown: [...years.keys()].sort((a, b) => a - b).map((year) => ({ year, months: years.get(year)! })),
  };
};
