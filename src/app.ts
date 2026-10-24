/**
 * Application Express (main.py) : CORS, lecture des corps de requête, routes dans le même ordre que FastAPI.
 */
import type { IncomingMessage } from 'node:http';
import cors from 'cors';
import express from 'express';
import { env } from './config/env.js';
import { backgroundTasksMiddleware } from './lib/background.js';
import { logger } from './lib/logger.js';
import { py, validateRequest, z } from './lib/validation.js';
import { authenticate, requireAdmin } from './middleware/auth.js';
import { errorHandler, notFoundHandler } from './middleware/errors.js';
import { adminRouter } from './modules/admin/admin.routes.js';
import { aiRouter } from './modules/ai/ai.routes.js';
import { analyticsRouter } from './modules/analytics/analytics.routes.js';
import { announcementsRouter } from './modules/announcements/announcements.routes.js';
import { authRouter } from './modules/auth/auth.routes.js';
import { allYouCanEatRouter } from './modules/catalog/all-you-can-eat.routes.js';
import { menusRouter } from './modules/catalog/menus.routes.js';
import { productsRouter } from './modules/catalog/products.routes.js';
import { customersRouter } from './modules/customers/customers.routes.js';
import { sendEmail } from './modules/email/email.service.js';
import { hubriseRouter } from './modules/hubrise/hubrise.routes.js';
import { ordersRouter } from './modules/orders/orders.routes.js';
import { promoCodesRouter } from './modules/promo-codes/promo-codes.routes.js';
import { reservationsRouter } from './modules/reservations/reservations.routes.js';
import { restaurantsRouter } from './modules/restaurants/restaurants.routes.js';
import { onboardingRouter } from './modules/onboarding/onboarding.routes.js';
import { internalRouter } from './modules/review-followups/internal.routes.js';
import { stripeRouter } from './modules/stripe/stripe.routes.js';
import { tablesRouter } from './modules/tables/tables.routes.js';
import { uploadsRouter } from './modules/uploads/uploads.routes.js';

/** Webhooks : le corps brut est nécessaire pour vérifier la signature. */
const RAW_BODY_PATHS = ['/stripe/webhooks', '/integrations/hubrise/webhook'];

/** Comme FastAPI : un corps sans Content-Type est lu comme du JSON. */
const isJsonRequest = (req: IncomingMessage) => {
  const contentType = req.headers['content-type'];
  if (!contentType) return true;
  const [type = ''] = contentType.split(';');
  const [main, sub = ''] = type.trim().toLowerCase().split('/');
  return main === 'application' && (sub === 'json' || sub.endsWith('+json'));
};

export const createApp = () => {
  const app = express();
  app.set('case sensitive routing', true);
  app.set('trust proxy', true);
  app.disable('x-powered-by');

  // Réponse 200 aux requêtes préalables (preflight), comme le CORSMiddleware de Starlette.
  // La page publique du questionnaire est toujours autorisée, sans avoir à modifier CORS_ALLOWED_ORIGINS.
  const origins = env.ONBOARDING_FORM_URL ? [...env.CORS_ALLOWED_ORIGINS, new URL(env.ONBOARDING_FORM_URL).origin] : env.CORS_ALLOWED_ORIGINS;
  app.use(cors({ origin: origins, credentials: true, optionsSuccessStatus: 200 }));
  app.use(RAW_BODY_PATHS, express.raw({ type: () => true, limit: '5mb' }));
  app.use(express.json({ type: isJsonRequest, limit: '10mb' }));
  app.use(express.urlencoded({ extended: false, limit: '10mb' }));
  // Autres corps (texte, XML…) : gardés tels quels pour être refusés comme par FastAPI. Les formulaires multipart sont lus par multer.
  app.use(express.text({ type: (req) => !isJsonRequest(req) && !/^(multipart\/form-data|application\/x-www-form-urlencoded)/i.test(req.headers['content-type'] ?? ''), limit: '10mb' }));
  app.use(backgroundTasksMiddleware);
  app.use((req, res, next) => {
    const start = process.hrtime.bigint();
    res.on('finish', () => {
      const ms = Number(process.hrtime.bigint() - start) / 1e6;
      logger.info({ method: req.method, path: req.originalUrl, status: res.statusCode, ms: Math.round(ms) }, 'request');
    });
    next();
  });

  app.use(authRouter);
  app.use(restaurantsRouter);
  app.use(adminRouter);
  app.use(productsRouter);
  app.use(menusRouter);
  app.use(uploadsRouter);
  app.use(allYouCanEatRouter);
  app.use(tablesRouter);
  app.use(reservationsRouter);
  app.use(ordersRouter);
  app.use(analyticsRouter);
  app.use(customersRouter);
  app.use(aiRouter);
  app.use(stripeRouter);
  app.use(hubriseRouter);
  app.use(promoCodesRouter);
  app.use(announcementsRouter);
  app.use(internalRouter);
  app.use(onboardingRouter);

  app.get('/', (_req, res) => {
    res.json({ message: 'Yumco API is running' });
  });

  /** E-mail de test. Correction de sécurité : réservé aux admins (public en Python). */
  app.get('/test-email', ...(env.STRICT_RESTAURANT_ACCESS ? [authenticate, requireAdmin] : []), async (req, res) => {
    const { query } = validateRequest(req, { query: z.object({ email: py.str() }) });
    await sendEmail({ to: query.email, subject: 'Test Email', body: '<h1>This is a test email</h1>' });
    res.json({ message: 'Test email sent' });
  });

  app.use(notFoundHandler);
  app.use(errorHandler);
  return app;
};
