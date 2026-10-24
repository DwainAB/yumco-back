/**
 * Temps de préparation des commandes (performance_analytics_service.py).
 */
import { prisma } from '../../db/prisma.js';
import { pyRound } from '../../lib/python.js';
import { nowIn, periodBounds, zoneOf } from '../../lib/time.js';
import { toFloat } from './analytics.helpers.js';

const averagePreparation = async (restaurantId: number, from: Date, to: Date) => {
  const [row] = await prisma.$queryRaw<{ average: unknown }[]>`
    SELECT coalesce(avg(extract(epoch FROM (o.completed_at - o.created_at)) / 60.0), 0) AS average
    FROM orders o
    WHERE o.restaurant_id = ${restaurantId} AND o.status != 'cancelled' AND o.preparing_by IS NOT NULL AND o.completed_at IS NOT NULL
      AND o.completed_at >= ${from} AND o.completed_at < ${to}`;
  return toFloat(row.average);
};

export const getPerformanceAnalytics = async (restaurantId: number) => {
  const restaurant = await prisma.restaurant.findUnique({ where: { id: restaurantId } });
  if (!restaurant) return null;

  const bounds = periodBounds(nowIn(zoneOf(restaurant.timezone)));
  const currentMonth = await averagePreparation(restaurantId, bounds.month_start_utc, bounds.next_month_start_utc);
  const previousMonth = await averagePreparation(restaurantId, bounds.previous_month_start_utc, bounds.month_start_utc);

  const preparers = await prisma.$queryRaw<{ user_id: number; first_name: string; prepared_orders_count: number; average: unknown }[]>`
    SELECT u.id AS user_id, u.first_name, count(o.id)::int AS prepared_orders_count,
           coalesce(avg(extract(epoch FROM (o.completed_at - o.created_at)) / 60.0), 0) AS average
    FROM users u JOIN roles r ON r.user_id = u.id JOIN orders o ON o.preparing_by = u.id
    WHERE r.restaurant_id = ${restaurantId} AND o.restaurant_id = ${restaurantId} AND o.status != 'cancelled' AND o.completed_at IS NOT NULL
    GROUP BY u.id, u.first_name ORDER BY count(o.id) DESC, u.first_name ASC`;

  return {
    preparation_time: {
      average_minutes: pyRound(currentMonth, 2),
      difference_vs_previous_month_minutes: pyRound(currentMonth - previousMonth, 2),
    },
    preparers: preparers.map((row) => ({
      user_id: row.user_id,
      first_name: row.first_name,
      prepared_orders_count: row.prepared_orders_count,
      average_preparation_minutes: pyRound(toFloat(row.average), 2),
    })),
  };
};
