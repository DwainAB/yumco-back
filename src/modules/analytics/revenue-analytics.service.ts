/**
 * Statistiques de chiffre d'affaires (revenue_analytics_service.py).
 */
import { prisma } from '../../db/prisma.js';
import { Prisma } from '../../generated/prisma/client.js';
import { pyRound } from '../../lib/python.js';
import { nowIn, periodBounds, zoneOf } from '../../lib/time.js';
import { dayLabel, MONTH_LABELS, monthLabel, percentageChange, toFloat } from './analytics.helpers.js';

const activeOrders = (restaurantId: number) => Prisma.sql`o.restaurant_id = ${restaurantId} AND o.status != 'cancelled'`;

const periodRevenue = async (restaurantId: number, from: Date, to: Date) => {
  const [row] = await prisma.$queryRaw<{ revenue: unknown; average: unknown }[]>`
    SELECT coalesce(sum(o.amount_total), 0) AS revenue, coalesce(avg(o.amount_total), 0) AS average
    FROM orders o WHERE ${activeOrders(restaurantId)} AND o.created_at >= ${from} AND o.created_at < ${to}`;
  return { revenue: toFloat(row.revenue), average: toFloat(row.average) };
};

export const getRevenueAnalytics = async (restaurantId: number) => {
  const restaurant = await prisma.restaurant.findUnique({ where: { id: restaurantId } });
  if (!restaurant) return null;

  const zone = zoneOf(restaurant.timezone);
  const bounds = periodBounds(nowIn(zone));
  const local = Prisma.sql`timezone(${zone}, o.created_at)`;

  const currentMonth = await periodRevenue(restaurantId, bounds.month_start_utc, bounds.next_month_start_utc);
  const previousMonth = await periodRevenue(restaurantId, bounds.previous_month_start_utc, bounds.month_start_utc);
  const currentYear = await periodRevenue(restaurantId, bounds.current_year_start_utc, bounds.next_year_start_utc);
  const previousYear = await periodRevenue(restaurantId, bounds.previous_year_start_utc, bounds.current_year_start_utc);

  const channelRows = await prisma.$queryRaw<{ year_value: number; order_type: string; amount: unknown }[]>`
    SELECT extract(year FROM ${local})::int AS year_value, o.type AS order_type, coalesce(sum(o.amount_total), 0) AS amount
    FROM orders o WHERE ${activeOrders(restaurantId)} AND o.type IN ('delivery', 'pickup')
    GROUP BY year_value, o.type ORDER BY year_value, o.type`;
  const channels = new Map<number, { delivery: number; pickup: number }>();
  for (const row of channelRows) {
    const entry = channels.get(row.year_value) ?? { delivery: 0, pickup: 0 };
    if (row.order_type === 'delivery') entry.delivery = pyRound(toFloat(row.amount), 2);
    if (row.order_type === 'pickup') entry.pickup = pyRound(toFloat(row.amount), 2);
    channels.set(row.year_value, entry);
  }

  const monthRows = await prisma.$queryRaw<{ year_value: number; month_value: number; amount: unknown }[]>`
    SELECT extract(year FROM ${local})::int AS year_value, extract(month FROM ${local})::int AS month_value,
           coalesce(sum(o.amount_total), 0) AS amount
    FROM orders o WHERE ${activeOrders(restaurantId)}
    GROUP BY year_value, month_value ORDER BY year_value, month_value`;
  const years = new Map<number, { total: number; months: { month: number; amount: number }[] }>();
  for (const row of monthRows) {
    const amount = pyRound(toFloat(row.amount), 2);
    const entry = years.get(row.year_value) ?? { total: 0, months: [] };
    entry.total += amount;
    entry.months.push({ month: row.month_value, amount });
    years.set(row.year_value, entry);
  }

  // Les regroupements utilisent les alias : chaque ${local} devient un paramètre distinct pour PostgreSQL.
  const [bestMonth] = await prisma.$queryRaw<{ year: number; month: number; amount: unknown }[]>`
    SELECT extract(year FROM bucket)::int AS year, extract(month FROM bucket)::int AS month, amount FROM (
      SELECT date_trunc('month', ${local}) AS bucket, coalesce(sum(o.amount_total), 0) AS amount
      FROM orders o WHERE ${activeOrders(restaurantId)}
      GROUP BY bucket ORDER BY sum(o.amount_total) DESC, bucket ASC LIMIT 1
    ) best`;

  const [bestDay] = await prisma.$queryRaw<{ year: number; month: number; day: number; amount: unknown }[]>`
    SELECT extract(year FROM bucket)::int AS year, extract(month FROM bucket)::int AS month, extract(day FROM bucket)::int AS day, amount FROM (
      SELECT date_trunc('day', ${local}) AS bucket, coalesce(sum(o.amount_total), 0) AS amount
      FROM orders o WHERE ${activeOrders(restaurantId)}
      GROUP BY bucket ORDER BY sum(o.amount_total) DESC, bucket ASC LIMIT 1
    ) best`;

  const sortedYears = (map: Map<number, unknown>) => [...map.keys()].sort((a, b) => a - b);
  const share = (part: number, total: number) => (total ? pyRound((part / total) * 100, 2) : 0);

  return {
    current_month_amount: pyRound(currentMonth.revenue, 2),
    current_month_change_percentage: percentageChange(currentMonth.revenue, previousMonth.revenue),
    previous_month_amount: pyRound(previousMonth.revenue, 2),
    yearly_channels: sortedYears(channels).map((year) => {
      const { delivery, pickup } = channels.get(year)!;
      const total = delivery + pickup;
      return {
        year,
        delivery: { amount: delivery, percentage: share(delivery, total) },
        pickup: { amount: pickup, percentage: share(pickup, total) },
      };
    }),
    best_month: {
      label: bestMonth ? monthLabel(bestMonth.month, bestMonth.year) : null,
      amount: bestMonth ? pyRound(toFloat(bestMonth.amount), 2) : 0,
    },
    best_day: {
      label: bestDay ? dayLabel(bestDay.day, bestDay.month, bestDay.year) : null,
      amount: bestDay ? pyRound(toFloat(bestDay.amount), 2) : 0,
    },
    yearly_breakdown: sortedYears(years).map((year) => {
      const entry = years.get(year)!;
      const total = pyRound(entry.total, 2);
      return {
        year,
        total_amount: total,
        months: entry.months.map((month) => ({ month: MONTH_LABELS[month.month], amount: month.amount, annual_percentage: share(month.amount, total) })),
      };
    }),
    annual_growth_percentage: percentageChange(currentYear.revenue, previousYear.revenue),
    average_basket: {
      amount: pyRound(currentMonth.average, 2),
      change_percentage_vs_previous_month: percentageChange(currentMonth.average, previousMonth.average),
    },
  };
};
