/**
 * Statistiques (routes/revenue.py, performance.py, customer_analytics.py).
 */
import { Router } from 'express';
import { notFound } from '../../lib/http-error.js';
import { intParams, validateRequest } from '../../lib/validation.js';
import { restaurantMember } from '../../middleware/auth.js';
import { getCustomerAnalytics } from './customer-analytics.service.js';
import { getPerformanceAnalytics } from './performance-analytics.service.js';
import { getRevenueAnalytics } from './revenue-analytics.service.js';

export const analyticsRouter = Router();

const restaurantParams = intParams('restaurant_id');

const analyticsRoute = (path: string, compute: (restaurantId: number) => Promise<unknown>) =>
  analyticsRouter.get(`/restaurants/:restaurant_id/${path}`, ...restaurantMember, async (req, res) => {
    const { params } = validateRequest(req, { params: restaurantParams });
    const analytics = await compute(params.restaurant_id);
    if (!analytics) throw notFound('Restaurant not found');
    res.json(analytics);
  });

analyticsRoute('revenue/analytics', getRevenueAnalytics);
analyticsRoute('performance/analytics', getPerformanceAnalytics);
analyticsRoute('customers/analytics', getCustomerAnalytics);
