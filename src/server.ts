/**
 * Démarrage du serveur HTTP (équivalent de `uvicorn main:app`).
 */
import { env } from './config/env.js';
import { createApp } from './app.js';
import { prisma } from './db/prisma.js';
import { flushBackgroundTasks } from './lib/background.js';
import { logger } from './lib/logger.js';

const server = createApp().listen(env.PORT, '0.0.0.0', () => {
  logger.info({ port: env.PORT, strictRestaurantAccess: env.STRICT_RESTAURANT_ACCESS }, 'Yumco API is running');
});

/** Arrêt propre : on termine les requêtes et les tâches de fond en cours avant de fermer la base. */
const shutdown = (signal: string) => {
  logger.info({ signal }, 'shutting down');
  server.close(async () => {
    await flushBackgroundTasks();
    await prisma.$disconnect();
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 25_000).unref();
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
