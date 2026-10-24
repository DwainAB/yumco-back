/**
 * Tâches lancées après l'envoi de la réponse (BackgroundTasks de FastAPI) : e-mails, notifications, HubRise.
 * Elles s'exécutent dans l'ordre d'ajout ; contrairement à Starlette, l'échec de l'une n'empêche pas les suivantes.
 */
import type { NextFunction, Request, Response } from 'express';
import { logger } from './logger.js';

type Task = { name: string; run: () => Promise<unknown> | unknown };

const pending = new Set<Promise<void>>();

const runTasks = async (tasks: Task[]) => {
  for (const task of tasks) {
    try {
      await task.run();
    } catch (error) {
      logger.error({ err: error, task: task.name }, '[background] task failed');
    }
  }
};

/** Lance des tâches sans attendre (hors requête, ex. webhook déjà répondu). */
export const runInBackground = (tasks: Task[]) => {
  const promise = runTasks(tasks).finally(() => pending.delete(promise));
  pending.add(promise);
};

/** Attend la fin des tâches en cours (tests, arrêt propre du serveur). */
export const flushBackgroundTasks = async () => {
  while (pending.size) await Promise.all([...pending]);
};

declare module 'express-serve-static-core' {
  interface Locals {
    backgroundTasks?: Task[];
  }
}

/** Ajoute une tâche à exécuter après la réponse. */
export const addBackgroundTask = (res: Response, name: string, run: Task['run']) => {
  (res.locals.backgroundTasks ??= []).push({ name, run });
};

/** Middleware : déclenche les tâches une fois la réponse envoyée. */
export const backgroundTasksMiddleware = (_req: Request, res: Response, next: NextFunction) => {
  res.on('finish', () => {
    const tasks = res.locals.backgroundTasks;
    if (tasks?.length) runInBackground(tasks);
  });
  next();
};
