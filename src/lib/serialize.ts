/**
 * Formats JSON des réponses, alignés sur la sérialisation de Pydantic v2 (response_model de FastAPI).
 */
import { DateTime } from 'luxon';
import type { Prisma } from '../generated/prisma/client.js';

type DecimalLike = Prisma.Decimal | number | string;

/** Champ `Decimal` : texte avec deux décimales (colonnes Numeric(10, 2)), ex. "12.50". */
export const decimalString = (value: DecimalLike): string =>
  typeof value === 'object' ? value.toFixed(2) : Number(value).toFixed(2);

export const decimalStringOrNull = (value: DecimalLike | null | undefined): string | null =>
  value === null || value === undefined ? null : decimalString(value);

/** Champ `float` : nombre JSON, ex. 12.5. */
export const float = (value: DecimalLike | null | undefined): number => (value === null || value === undefined ? 0 : Number(value));

export const floatOrNull = (value: DecimalLike | null | undefined): number | null =>
  value === null || value === undefined ? null : Number(value);

const pad = (value: number, size = 2) => String(value).padStart(size, '0');

/** Date et heure en UTC : 2026-05-15T14:28:08.123Z (sans fraction si elle est nulle, comme Pydantic). */
export const datetime = (value: Date): string => {
  const iso = value.toISOString();
  return value.getUTCMilliseconds() === 0 ? iso.replace('.000Z', 'Z') : iso;
};

export const datetimeOrNull = (value: Date | null | undefined): string | null => (value ? datetime(value) : null);

/** Date et heure dans un fuseau : 2026-05-15T16:28:08+02:00 (isoformat() de Python). */
export const localDatetime = (value: DateTime): string =>
  value.toISO({ suppressMilliseconds: true, includeOffset: true }) ?? '';

/** Colonne `date` : 2026-05-15. */
export const date = (value: Date): string =>
  `${value.getUTCFullYear()}-${pad(value.getUTCMonth() + 1)}-${pad(value.getUTCDate())}`;

/** Colonne `time` : 19:30:00 (fraction ajoutée seulement si elle existe, comme time.isoformat()). */
export const time = (value: Date): string => {
  const base = `${pad(value.getUTCHours())}:${pad(value.getUTCMinutes())}:${pad(value.getUTCSeconds())}`;
  const ms = value.getUTCMilliseconds();
  return ms ? `${base}.${pad(ms, 3)}000` : base;
};
