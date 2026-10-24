/**
 * Réponses d'erreur au format FastAPI.
 */
import type { NextFunction, Request, Response } from 'express';
import { HttpError } from '../lib/http-error.js';
import { logger } from '../lib/logger.js';
import { RequestValidationError } from '../lib/validation.js';

export const notFoundHandler = (_req: Request, res: Response) => {
  res.status(404).json({ detail: 'Not Found' });
};

type BodyParserError = Error & { type?: string; status?: number; body?: unknown };

export const errorHandler = (error: unknown, req: Request, res: Response, _next: NextFunction) => {
  if (res.headersSent) return;

  if (error instanceof HttpError) {
    res.set(error.headers).status(error.status).json({ detail: error.detail });
    return;
  }

  if (error instanceof RequestValidationError) {
    res.status(422).json({ detail: error.errors });
    return;
  }

  const bodyError = error as BodyParserError;
  if (bodyError?.type === 'entity.parse.failed') {
    // Position du caractère fautif, comme le message de json.loads côté Python.
    const position = Number(/position (\d+)/.exec(bodyError.message)?.[1] ?? 0);
    res.status(422).json({
      detail: [{ type: 'json_invalid', loc: ['body', position], msg: 'JSON decode error', input: {}, ctx: { error: bodyError.message } }],
    });
    return;
  }
  if (bodyError?.type === 'entity.too.large') {
    res.status(413).json({ detail: 'Request Entity Too Large' });
    return;
  }

  logger.error({ err: error, method: req.method, path: req.originalUrl }, 'Unhandled error');
  res.status(500).json({ detail: 'Internal Server Error' });
};
