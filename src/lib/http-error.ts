/** Erreur HTTP renvoyée au client sous la forme `{"detail": ...}` (équivalent de HTTPException). */
export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
    readonly headers: Record<string, string> = {},
  ) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail));
    this.name = 'HttpError';
  }
}

export const badRequest = (detail: unknown) => new HttpError(400, detail);
export const unauthorized = (detail: unknown, headers?: Record<string, string>) => new HttpError(401, detail, headers);
export const forbidden = (detail: unknown) => new HttpError(403, detail);
export const notFound = (detail: unknown) => new HttpError(404, detail);
export const conflict = (detail: unknown) => new HttpError(409, detail);
export const badGateway = (detail: unknown) => new HttpError(502, detail);
export const serviceUnavailable = (detail: unknown) => new HttpError(503, detail);
export const internalError = (detail: unknown) => new HttpError(500, detail);
