/**
 * Routes internes appelées par une tâche planifiée (routes/internal.py).
 */
import { timingSafeEqual } from 'node:crypto';
import { Router } from 'express';
import { env } from '../../config/env.js';
import { internalError, unauthorized } from '../../lib/http-error.js';
import { ge, le, py, validateRequest, z } from '../../lib/validation.js';
import { processDueReviewFollowups } from './review-followups.service.js';

const sameSecret = (a: string, b: string) => {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
};

export const internalRouter = Router();

internalRouter.post('/internal/review-followups/process', async (req, res) => {
  const { query } = validateRequest(req, { query: z.object({ limit: py.int().superRefine(ge(1)).superRefine(le(500)).default(100) }) });
  if (!env.REVIEW_FOLLOWUPS_CRON_SECRET) throw internalError('REVIEW_FOLLOWUPS_CRON_SECRET is not configured');
  const secret = req.header('x-cron-secret');
  if (!secret || !sameSecret(secret, env.REVIEW_FOLLOWUPS_CRON_SECRET)) throw unauthorized('Invalid cron secret');
  res.json(await processDueReviewFollowups(query.limit));
});
