/**
 * Statistiques de commandes (order_analytics_service.py).
 */
import { prisma } from '../../db/prisma.js';
import { Prisma } from '../../generated/prisma/client.js';
import { pyMod, pyRound } from '../../lib/python.js';
import { datetime } from '../../lib/serialize.js';
import { nowIn, periodBounds, zoneOf } from '../../lib/time.js';
import { monthLabel, percentageChange, toFloat, toInt, WEEKDAY_LABELS } from './analytics.helpers.js';

/** Commandes prises en compte : celles du restaurant qui ne sont pas annulées. */
const activeOrders = (restaurantId: number) => Prisma.sql`o.restaurant_id = ${restaurantId} AND o.status != 'cancelled'`;

const between = (from: Date, to: Date) => Prisma.sql`o.created_at >= ${from} AND o.created_at < ${to}`;

const periodStats = async (restaurantId: number, from: Date, to: Date) => {
  const [row] = await prisma.$queryRaw<{ count: number; revenue: unknown; average: unknown }[]>`
    SELECT count(*)::int AS count, coalesce(sum(o.amount_total), 0) AS revenue, coalesce(avg(o.amount_total), 0) AS average
    FROM orders o WHERE ${activeOrders(restaurantId)} AND ${between(from, to)}`;
  return { count: row.count, revenue: toFloat(row.revenue), average: toFloat(row.average) };
};

export const getOrderAnalytics = async (restaurantId: number) => {
  const restaurant = await prisma.restaurant.findUnique({ where: { id: restaurantId } });
  if (!restaurant) return null;

  const zone = zoneOf(restaurant.timezone);
  const bounds = periodBounds(nowIn(zone));
  const local = Prisma.sql`timezone(${zone}, o.created_at)`;

  const topItems = await prisma.$queryRaw<{ item_name: string; quantity_sold: unknown; revenue: unknown; item_type: string }[]>`
    SELECT oi.name AS item_name, sum(oi.quantity) AS quantity_sold, sum(oi.subtotal) AS revenue,
           CASE WHEN oi.product_id IS NOT NULL THEN 'product' ELSE 'menu_choice' END AS item_type
    FROM order_items oi JOIN orders o ON o.id = oi.order_id
    WHERE ${activeOrders(restaurantId)} AND (oi.product_id IS NOT NULL OR oi.menu_option_id IS NOT NULL)
    GROUP BY oi.name, oi.product_id, oi.menu_option_id, item_type
    ORDER BY sum(oi.quantity) DESC, sum(oi.subtotal) DESC
    LIMIT 10`;

  const currentMonth = await periodStats(restaurantId, bounds.month_start_utc, bounds.next_month_start_utc);
  const previousMonth = await periodStats(restaurantId, bounds.previous_month_start_utc, bounds.month_start_utc);
  const currentYear = await periodStats(restaurantId, bounds.current_year_start_utc, bounds.next_year_start_utc);
  const previousYear = await periodStats(restaurantId, bounds.previous_year_start_utc, bounds.current_year_start_utc);

  const typeRows = await prisma.$queryRaw<{ type: string; orders_count: number }[]>`
    SELECT o.type, count(o.id)::int AS orders_count FROM orders o
    WHERE ${activeOrders(restaurantId)} AND o.type IN ('delivery', 'pickup') GROUP BY o.type`;
  const deliveryCount = typeRows.find((row) => row.type === 'delivery')?.orders_count ?? 0;
  const pickupCount = typeRows.find((row) => row.type === 'pickup')?.orders_count ?? 0;
  const onlineTotal = deliveryCount + pickupCount;

  const cities = await prisma.$queryRaw<{ city: string; orders_count: number }[]>`
    SELECT a.city, count(o.id)::int AS orders_count
    FROM addresses a JOIN orders o ON o.address_id = a.id
    WHERE ${activeOrders(restaurantId)} AND o.type = 'delivery'
    GROUP BY a.city ORDER BY count(o.id) DESC, a.city ASC LIMIT 10`;

  // Les regroupements utilisent les alias : chaque ${local} devient un paramètre distinct pour PostgreSQL.
  const [bestMonth] = await prisma.$queryRaw<{ year: number; month: number; orders_count: number }[]>`
    SELECT extract(year FROM bucket)::int AS year, extract(month FROM bucket)::int AS month, orders_count FROM (
      SELECT date_trunc('month', ${local}) AS bucket, count(o.id)::int AS orders_count
      FROM orders o WHERE ${activeOrders(restaurantId)}
      GROUP BY bucket ORDER BY orders_count DESC, bucket ASC LIMIT 1
    ) best`;

  const [largestOrder] = await prisma.$queryRaw<{ amount_total: unknown; created_at: Date }[]>`
    SELECT o.amount_total, o.created_at FROM orders o WHERE ${activeOrders(restaurantId)}
    ORDER BY o.amount_total DESC, o.created_at DESC LIMIT 1`;

  const weekdays = await prisma.$queryRaw<{ weekday: number; orders_count: number }[]>`
    SELECT extract(dow FROM ${local})::int AS weekday, count(o.id)::int AS orders_count
    FROM orders o WHERE ${activeOrders(restaurantId)}
    GROUP BY weekday ORDER BY orders_count DESC, weekday ASC`;

  const hours = await prisma.$queryRaw<{ hour_of_day: number; orders_count: number }[]>`
    SELECT extract(hour FROM ${local})::int AS hour_of_day, count(o.id)::int AS orders_count
    FROM orders o WHERE ${activeOrders(restaurantId)} GROUP BY hour_of_day`;
  const hourlyCounts = new Map(hours.map((row) => [row.hour_of_day, row.orders_count]));
  let busiestSlot: { slot: string | null; orders_count: number } = { slot: null, orders_count: 0 };
  for (let startHour = 0; startHour < 23; startHour += 1) {
    const count = (hourlyCounts.get(startHour) ?? 0) + (hourlyCounts.get(startHour + 1) ?? 0);
    if (count > busiestSlot.orders_count) {
      const pad = (hour: number) => String(hour).padStart(2, '0');
      busiestSlot = { slot: `${pad(startHour)}:00-${pad((startHour + 2) % 24)}:00`, orders_count: count };
    }
  }

  // Client identifié par son e-mail, sinon par les chiffres de son téléphone.
  const customerRows = await prisma.$queryRaw<{ email_key: string | null; phone_key: string; orders_count: number }[]>`
    SELECT lower(trim(c.email)) AS email_key, regexp_replace(coalesce(c.phone, ''), '\\D', '', 'g') AS phone_key, count(o.id)::int AS orders_count
    FROM customers c JOIN orders o ON o.customer_id = c.id
    WHERE ${activeOrders(restaurantId)}
    GROUP BY lower(trim(c.email)), regexp_replace(coalesce(c.phone, ''), '\\D', '', 'g'), c.id`;
  const buckets = new Map<string, number>();
  for (const row of customerRows) {
    const identity = row.email_key || row.phone_key || null;
    if (!identity) continue;
    buckets.set(identity, (buckets.get(identity) ?? 0) + row.orders_count);
  }
  const identifiableCustomers = buckets.size;
  const repeatCustomers = [...buckets.values()].filter((count) => count >= 2).length;

  return {
    top_items: topItems.map((row) => ({
      item_name: row.item_name,
      item_type: row.item_type,
      quantity_sold: toInt(row.quantity_sold),
      revenue: pyRound(toFloat(row.revenue), 2),
    })),
    monthly_orders_count: currentMonth.count,
    monthly_orders_change: currentMonth.count - previousMonth.count,
    monthly_orders_change_percentage: percentageChange(currentMonth.count, previousMonth.count),
    monthly_revenue_change_percentage: percentageChange(currentMonth.revenue, previousMonth.revenue),
    delivery_percentage: onlineTotal ? pyRound((deliveryCount / onlineTotal) * 100, 2) : 0,
    pickup_percentage: onlineTotal ? pyRound((pickupCount / onlineTotal) * 100, 2) : 0,
    top_delivery_cities: cities.map((row) => ({ city: row.city, orders_count: row.orders_count })),
    best_month: {
      label: bestMonth ? monthLabel(bestMonth.month, bestMonth.year) : null,
      orders_count: bestMonth?.orders_count ?? 0,
    },
    largest_order: largestOrder ? { amount: pyRound(toFloat(largestOrder.amount_total), 2), created_at: datetime(largestOrder.created_at) } : null,
    current_year_orders_count: currentYear.count,
    average_basket: {
      amount: pyRound(currentYear.average, 2),
      change_percentage_vs_previous_year: percentageChange(currentYear.average, previousYear.average),
    },
    busiest_days: weekdays.map((row) => ({ day: WEEKDAY_LABELS[pyMod(row.weekday - 1, 7)], orders_count: row.orders_count })),
    busiest_time_slot: busiestSlot,
    repeat_purchase: {
      rate_percentage: identifiableCustomers ? pyRound((repeatCustomers / identifiableCustomers) * 100, 2) : null,
      repeat_customers: repeatCustomers,
      identifiable_customers: identifiableCustomers,
    },
  };
};
