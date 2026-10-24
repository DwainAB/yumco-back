/**
 * Validation des entrées avec les règles de Pydantic v2 (mode « lax ») :
 * mêmes conversions ("5" → 5 pour un entier, "true"/"1"/"yes" pour un booléen…),
 * champs inconnus ignorés, champs absents laissés absents (équivalent de exclude_unset),
 * et erreurs 422 au format de FastAPI : {"detail": [{"type", "loc", "msg", "input"}]}.
 */
import type { Request } from 'express';
import * as z from 'zod';
import { Prisma } from '../generated/prisma/client.js';

type Ctx = z.core.$RefinementCtx;

/**
 * Ajoute une erreur au format Pydantic : `type`, message et éventuel `ctx`.
 * La valeur reçue (`input`) est retrouvée plus tard dans la requête brute, comme Pydantic qui renvoie l'entrée d'origine.
 */
const issue = (ctx: Ctx, type: string, msg: string, errorCtx?: Record<string, unknown>, path?: PropertyKey[]) =>
  ctx.addIssue({ code: 'custom', message: msg, params: { type, ...(errorCtx ? { ctx: errorCtx } : {}) }, ...(path ? { path } : {}) });

const fail = (ctx: Ctx, type: string, msg: string, _input?: unknown, errorCtx?: Record<string, unknown>): never => {
  issue(ctx, type, msg, errorCtx);
  return z.NEVER as never;
};

/** Message d'un validateur métier (field_validator qui lève ValueError). */
export const valueError = (ctx: Ctx, message: string, path?: PropertyKey[], _input?: unknown) =>
  issue(ctx, 'value_error', `Value error, ${message}`, { error: {} }, path);

/** Champ obligatoire : `undefined` donne l'erreur « Field required ». */
const present = () => z.custom<unknown>((value) => value !== undefined, { message: 'Field required', params: { type: 'missing' } });

const scalar = <T>(convert: (value: unknown, ctx: Ctx) => T) => present().transform((value, ctx): T => convert(value, ctx));

/* ---------- Types scalaires ---------- */

const INT_STRING = /^\s*[-+]?\d+\s*$/;
const NUMBER_STRING = /^\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*$/;

const toInt = (value: unknown, ctx: Ctx): number => {
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return value;
    if (Number.isFinite(value)) return fail(ctx, 'int_from_float', 'Input should be a valid integer, got a number with a fractional part', value);
  }
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (typeof value === 'string') {
    if (INT_STRING.test(value)) return Number(value.trim());
    return fail(ctx, 'int_parsing', 'Input should be a valid integer, unable to parse string as an integer', value);
  }
  return fail(ctx, 'int_type', 'Input should be a valid integer', value);
};

const toFloat = (value: unknown, ctx: Ctx): number => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (typeof value === 'string' && NUMBER_STRING.test(value)) return Number(value.trim());
  if (typeof value === 'string') return fail(ctx, 'float_parsing', 'Input should be a valid number, unable to parse string as a number', value);
  return fail(ctx, 'float_type', 'Input should be a valid number', value);
};

const toDecimal = (value: unknown, ctx: Ctx): Prisma.Decimal => {
  if (typeof value === 'number' && Number.isFinite(value)) return new Prisma.Decimal(String(value));
  if (typeof value === 'string' && NUMBER_STRING.test(value)) return new Prisma.Decimal(value.trim());
  if (typeof value === 'string') return fail(ctx, 'decimal_parsing', 'Input should be a valid decimal', value);
  return fail(ctx, 'decimal_type', 'Decimal input should be an integer, float, string or Decimal object', value);
};

const TRUE_VALUES = new Set(['1', 'on', 't', 'true', 'y', 'yes']);
const FALSE_VALUES = new Set(['0', 'off', 'f', 'false', 'n', 'no']);

const toBool = (value: unknown, ctx: Ctx): boolean => {
  if (typeof value === 'boolean') return value;
  if (value === 0 || value === 1) return value === 1;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (TRUE_VALUES.has(normalized)) return true;
    if (FALSE_VALUES.has(normalized)) return false;
    return fail(ctx, 'bool_parsing', 'Input should be a valid boolean, unable to interpret input', value);
  }
  return fail(ctx, 'bool_type', 'Input should be a valid boolean', value);
};

const toStr = (value: unknown, ctx: Ctx): string =>
  typeof value === 'string' ? value : fail(ctx, 'string_type', 'Input should be a valid string', value);

/* ---------- Dates et heures (règles de speedate, l'analyseur de Pydantic) ---------- */

const isDigits = (text: string) => /^\d+$/.test(text);

/** Raison du refus d'une date AAAA-MM-JJ (même texte que speedate), ou null si elle est valide. */
const dateError = (text: string): string | null => {
  if (text.length < 10) return 'input is too short';
  if (!isDigits(text.slice(0, 4))) return 'invalid character in year';
  if (text[4] !== '-') return 'invalid date separator, expected `-`';
  if (!isDigits(text.slice(5, 7))) return 'invalid character in month';
  if (text[7] !== '-') return 'invalid date separator, expected `-`';
  if (!isDigits(text.slice(8, 10))) return 'invalid character in day';
  const [year, month, day] = [Number(text.slice(0, 4)), Number(text.slice(5, 7)), Number(text.slice(8, 10))];
  if (month < 1 || month > 12) return 'month value is outside expected range of 1-12';
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  if (day < 1 || day > daysInMonth) return 'day value is outside expected range';
  return null;
};

interface ParsedTime {
  hours: number;
  minutes: number;
  seconds: number;
  ms: number;
  /** Décalage horaire en minutes, null sans fuseau. */
  offset: number | null;
}

/** Heure HH:MM[:SS[.ffffff]] avec fuseau facultatif ; renvoie la raison du refus si elle est invalide. */
const parseTime = (text: string): ParsedTime | string => {
  if (text.length < 5) return 'input is too short';
  if (!isDigits(text.slice(0, 2))) return 'invalid character in hour';
  if (text[2] !== ':') return 'invalid time separator, expected `:`';
  if (!isDigits(text.slice(3, 5))) return 'invalid character in minute';
  const hours = Number(text.slice(0, 2));
  const minutes = Number(text.slice(3, 5));
  if (hours > 23) return 'hour value is outside expected range of 0-23';
  if (minutes > 59) return 'minute value is outside expected range of 0-59';
  let rest = text.slice(5);
  let seconds = 0;
  let ms = 0;
  if (rest.startsWith(':')) {
    if (!isDigits(rest.slice(1, 3)) || rest.length < 3) return 'invalid character in second';
    seconds = Number(rest.slice(1, 3));
    if (seconds > 59) return 'second value is outside expected range of 0-59';
    rest = rest.slice(3);
    const fraction = /^[.,](\d{1,6})/.exec(rest);
    if (fraction) {
      ms = Number(fraction[1].padEnd(3, '0').slice(0, 3));
      rest = rest.slice(fraction[0].length);
    }
  }
  let offset: number | null = null;
  if (rest === 'Z' || rest === 'z') {
    offset = 0;
    rest = '';
  } else {
    const zone = /^([+-])(\d{2}):?(\d{2})?$/.exec(rest);
    if (zone) {
      const zoneHours = Number(zone[2]);
      const zoneMinutes = Number(zone[3] ?? '0');
      if (zoneHours > 23 || zoneMinutes > 59) return 'unexpected extra characters at the end of the input';
      offset = (zone[1] === '-' ? -1 : 1) * (zoneHours * 60 + zoneMinutes);
      rest = '';
    }
  }
  if (rest) return 'unexpected extra characters at the end of the input';
  return { hours, minutes, seconds, ms, offset };
};

const fromUnixTimestamp = (value: number) => new Date(Math.abs(value) > 2e10 ? value : value * 1000);

const dateUtc = (text: string) => Date.UTC(Number(text.slice(0, 4)), Number(text.slice(5, 7)) - 1, Number(text.slice(8, 10)));

/** Date et heure ISO 8601 (« T », « t », « _ » ou espace) ; sans fuseau, l'heure est prise en UTC comme en base. */
const parseDatetime = (text: string): Date | string => {
  const dateReason = dateError(text);
  if (dateReason) return dateReason;
  if (text.length === 10) return new Date(dateUtc(text));
  if (!'Tt _'.includes(text[10])) return 'unexpected extra characters at the end of the input';
  const time = parseTime(text.slice(11));
  // speedate se replie alors sur une date seule, d'où ce message pour toute heure invalide.
  if (typeof time === 'string') return 'unexpected extra characters at the end of the input';
  const local = dateUtc(text) + ((time.hours * 60 + time.minutes) * 60 + time.seconds) * 1000 + time.ms;
  return new Date(local - (time.offset ?? 0) * 60_000);
};

export const parseDatetimeString = (value: string): Date | null => {
  const parsed = parseDatetime(value.trim());
  return typeof parsed === 'string' ? null : parsed;
};

const toDatetime = (value: unknown, ctx: Ctx): Date => {
  if (typeof value === 'number' && Number.isFinite(value)) return fromUnixTimestamp(value);
  if (typeof value === 'string') {
    if (NUMBER_STRING.test(value)) return fromUnixTimestamp(Number(value));
    const parsed = parseDatetime(value);
    if (typeof parsed !== 'string') return parsed;
    return fail(ctx, 'datetime_from_date_parsing', `Input should be a valid datetime or date, ${parsed}`, value, { error: parsed });
  }
  return fail(ctx, 'datetime_type', 'Input should be a valid datetime', value);
};

const INEXACT_DATE = 'Datetimes provided to dates should have zero time - e.g. be exact dates';

/** Colonne `date` : une date seule, ou une date et heure à minuit pile. */
const toDate = (value: unknown, ctx: Ctx): Date => {
  const exact = (date: Date) =>
    date.getUTCHours() === 0 && date.getUTCMinutes() === 0 && date.getUTCSeconds() === 0 && date.getUTCMilliseconds() === 0
      ? new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()))
      : fail(ctx, 'date_from_datetime_inexact', INEXACT_DATE, value);
  if (typeof value === 'number' && Number.isFinite(value)) return exact(fromUnixTimestamp(value));
  if (typeof value === 'string') {
    if (NUMBER_STRING.test(value)) return exact(fromUnixTimestamp(Number(value)));
    const reason = dateError(value);
    if (reason) return fail(ctx, 'date_from_datetime_parsing', `Input should be a valid date or datetime, ${reason}`, value, { error: reason });
    if (value.length === 10) return new Date(dateUtc(value));
    const parsed = parseDatetime(value);
    if (typeof parsed === 'string') {
      return fail(ctx, 'date_from_datetime_parsing', `Input should be a valid date or datetime, ${parsed}`, value, { error: parsed });
    }
    return exact(parsed);
  }
  return fail(ctx, 'date_type', 'Input should be a valid date', value);
};

/** Heure sans date, stockée comme 1970-01-01THH:MM:SSZ (colonne `time` de Prisma). Le fuseau est ignoré, comme en base. */
const toTime = (value: unknown, ctx: Ctx): Date => {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value < 86_400) {
    return new Date(Math.round(value * 1000));
  }
  if (typeof value === 'string') {
    const parsed = parseTime(value);
    if (typeof parsed !== 'string') {
      return new Date(Date.UTC(1970, 0, 1, parsed.hours, parsed.minutes, parsed.seconds, parsed.ms));
    }
    return fail(ctx, 'time_parsing', `Input should be in a valid time format, ${parsed}`, value, { error: parsed });
  }
  return fail(ctx, 'time_type', 'Input should be a valid time', value);
};

const LOCAL_PART_CHAR = /[\p{L}\p{N}!#$%&'*+\-/=?^_`{|}~.]/u;
const DOMAIN_CHAR = /[\p{L}\p{N}\-.]/u;

const describeChars = (chars: string[]) =>
  [...new Set(chars)].map((char) => (char === ' ' ? 'SPACE' : `'${char}'`)).join(', ');

/** Raison du refus d'une adresse, avec les messages de la bibliothèque email-validator utilisée par Pydantic. */
const emailError = (email: string): string | null => {
  const at = email.indexOf('@');
  if (at === -1) return 'An email address must have an @-sign.';
  const local = email.slice(0, at);
  const domain = email.slice(at + 1);
  if (!local) return 'There must be something before the @-sign.';
  if (!domain) return 'There must be something after the @-sign.';
  const badLocal = [...local].filter((char) => !LOCAL_PART_CHAR.test(char));
  if (badLocal.length) return `The email address contains invalid characters before the @-sign: ${describeChars(badLocal)}.`;
  if (local.startsWith('.')) return 'An email address cannot start with a period.';
  if (local.endsWith('.')) return 'An email address cannot have a period immediately before the @-sign.';
  if (local.includes('..') || domain.includes('..')) return 'An email address cannot have two periods in a row.';
  const badDomain = [...domain].filter((char) => !DOMAIN_CHAR.test(char));
  if (badDomain.length) return `The part after the @-sign contains invalid characters: ${describeChars(badDomain)}.`;
  if (domain.startsWith('.')) return 'An email address cannot have a period immediately after the @-sign.';
  if (domain.endsWith('.')) return 'An email address cannot end with a period.';
  if (!domain.includes('.')) return 'The part after the @-sign is not valid. It should have a period.';
  return null;
};

/** EmailStr : adresse validée, nom de domaine mis en minuscules (forme normalisée d'email-validator). */
const toEmail = (value: unknown, ctx: Ctx): string => {
  const text = toStr(value, ctx);
  if (typeof text !== 'string') return text;
  const reason = emailError(text);
  if (reason) {
    return fail(ctx, 'value_error', `value is not a valid email address: ${reason}`, value, { reason });
  }
  const at = text.indexOf('@');
  return `${text.slice(0, at).normalize('NFC')}@${text.slice(at + 1).toLowerCase().normalize('NFC')}`;
};

/** HttpUrl : URL http(s) normalisée (un chemin vide devient « / »), comme str(HttpUrl). */
const toHttpUrl = (value: unknown, ctx: Ctx): string => {
  const text = toStr(value, ctx);
  if (typeof text !== 'string') return text;
  let url: URL;
  try {
    url = new URL(text.trim());
  } catch {
    const scheme = /^([a-z][a-z0-9+.-]*):(\/\/)?(.*)$/i.exec(text.trim());
    const reason = !scheme ? 'relative URL without a base' : !scheme[3] ? 'empty host' : 'invalid international domain name';
    return fail(ctx, 'url_parsing', `Input should be a valid URL, ${reason}`, value, { error: reason });
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return fail(ctx, 'url_scheme', "URL scheme should be 'http' or 'https'", value, { expected_schemes: "'http' or 'https'" });
  }
  return url.href;
};

/* ---------- Constructeurs ---------- */

export const py = {
  str: () => scalar(toStr),
  int: () => scalar(toInt),
  float: () => scalar(toFloat),
  decimal: () => scalar(toDecimal),
  bool: () => scalar(toBool),
  datetime: () => scalar(toDatetime),
  date: () => scalar(toDate),
  time: () => scalar(toTime),
  email: () => scalar(toEmail),
  httpUrl: () => scalar(toHttpUrl),
  /** Valeur parmi une liste (Literal[...]). */
  literal: <const T extends string>(...values: T[]) =>
    scalar((value, ctx): T => {
      if (typeof value === 'string' && (values as string[]).includes(value)) return value as T;
      const expected = values.map((v) => `'${v}'`);
      const msg = expected.length > 1 ? `${expected.slice(0, -1).join(', ')} or ${expected.at(-1)}` : expected[0];
      return fail(ctx, 'literal_error', `Input should be ${msg}`, value, { expected: msg });
    }),
  /** Champ JSON libre (dict[str, Any]). */
  dict: () =>
    scalar((value, ctx): Record<string, unknown> =>
      value !== null && typeof value === 'object' && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : fail(ctx, 'dict_type', 'Input should be a valid dictionary', value),
    ),
};

/* ---------- Validateurs de modèle ---------- */

/** model_validator(mode="after") : ne s'exécute que si tous les champs sont valides. */
export const MODEL_VALIDATOR = { when: (payload: z.core.ParsePayload) => payload.issues.length === 0 };

/** Validateur qui dépend de certains champs : il s'exécute si ces champs-là sont valides. */
export const afterFields = (...fields: string[]) => ({
  when: (payload: z.core.ParsePayload) => payload.issues.every((issue) => !fields.includes(String(issue.path?.[0]))),
});

/* ---------- Contraintes (Field(ge=…, le=…, min_length=…)) ---------- */

export const ge = (min: number) => (value: number | Prisma.Decimal, ctx: Ctx) => {
  if (Number(value) < min) issue(ctx, 'greater_than_equal', `Input should be greater than or equal to ${min}`, { ge: min });
};

export const le = (max: number) => (value: number, ctx: Ctx) => {
  if (value > max) issue(ctx, 'less_than_equal', `Input should be less than or equal to ${max}`, { le: max });
};

export const lengthBetween = (min: number, max?: number) => (value: string, ctx: Ctx) => {
  if (value.length < min) {
    issue(ctx, 'string_too_short', `String should have at least ${min} character${min > 1 ? 's' : ''}`, { min_length: min });
  } else if (max !== undefined && value.length > max) {
    issue(ctx, 'string_too_long', `String should have at most ${max} characters`, { max_length: max });
  }
};

export const maxItems = (max: number) => (value: unknown[], ctx: Ctx) => {
  if (value.length > max) {
    issue(ctx, 'too_long', `List should have at most ${max} items after validation, not ${value.length}`, {
      field_type: 'List',
      max_length: max,
      actual_length: value.length,
    });
  }
};

/** Texte qui doit respecter une expression régulière (Query(pattern=…)). */
export const matches = (pattern: string) => (value: string, ctx: Ctx) => {
  if (!new RegExp(pattern).test(value)) issue(ctx, 'string_pattern_mismatch', `String should match pattern '${pattern}'`, { pattern });
};

/* ---------- Erreurs 422 ---------- */

export type Loc = 'body' | 'query' | 'path' | 'header' | 'form';

export interface FastApiValidationError {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

export class RequestValidationError extends Error {
  constructor(readonly errors: FastApiValidationError[]) {
    super('Request validation failed');
    this.name = 'RequestValidationError';
  }
}

const valueAt = (root: unknown, path: PropertyKey[]): unknown => {
  let current: unknown = root;
  for (const key of path) {
    if (current === null || typeof current !== 'object') return undefined;
    current = (current as Record<PropertyKey, unknown>)[key];
  }
  return current;
};

const toFastApiError = (zodIssue: z.core.$ZodIssue, loc: Loc, root: unknown): FastApiValidationError => {
  const path = zodIssue.path.map((key) => (typeof key === 'number' ? key : String(key)));
  const fullLoc = [loc === 'form' ? 'body' : loc, ...path];
  // Pydantic renvoie la valeur telle qu'elle a été reçue (« 0 » en texte pour un paramètre d'URL).
  const input = valueAt(root, zodIssue.path);
  // Champ manquant : l'objet parent pour un corps JSON, null pour l'URL et les formulaires (paramètres validés un par un).
  const missingInput = loc === 'body' ? (valueAt(root, zodIssue.path.slice(0, -1)) ?? null) : null;
  const params = (zodIssue as { params?: { type?: string; ctx?: Record<string, unknown> } }).params;
  if (params?.type) {
    const error: FastApiValidationError = { type: params.type, loc: fullLoc, msg: zodIssue.message, input: params.type === 'missing' ? missingInput : input };
    if (params.ctx) error.ctx = params.ctx;
    return error;
  }
  if (zodIssue.code === 'invalid_type' && input === undefined) {
    return { type: 'missing', loc: fullLoc, msg: 'Field required', input: missingInput };
  }
  if (zodIssue.code === 'invalid_type' && zodIssue.expected === 'array') {
    return { type: 'list_type', loc: fullLoc, msg: 'Input should be a valid list', input };
  }
  if (zodIssue.code === 'invalid_type' && zodIssue.expected === 'object') {
    return { type: 'model_attributes_type', loc: fullLoc, msg: 'Input should be a valid dictionary or object to extract fields from', input };
  }
  return { type: 'value_error', loc: fullLoc, msg: zodIssue.message, input };
};

type Shape = z.ZodType;

interface RequestSchemas {
  params?: Shape;
  query?: Shape;
  body?: Shape;
  /** Champs d'un formulaire multipart (les valeurs vides valent « non envoyé », comme Form()). */
  form?: Shape;
}

type Output<S> = S extends z.ZodType ? z.output<S> : undefined;

/** Ne garde que la dernière valeur d'un paramètre répété (comportement de Starlette). */
const lastValues = (query: Record<string, unknown>) =>
  Object.fromEntries(Object.entries(query).map(([key, value]) => [key, Array.isArray(value) ? value.at(-1) : value]));

const withoutEmptyStrings = (form: Record<string, unknown>) =>
  Object.fromEntries(
    Object.entries(form)
      .map(([key, value]) => [key, Array.isArray(value) ? value.filter((item) => item !== '') : value] as const)
      .filter(([, value]) => value !== '' && !(Array.isArray(value) && value.length === 0)),
  );

/**
 * Valide les paramètres de chemin, de requête et le corps d'une requête en une fois.
 * Toutes les erreurs sont renvoyées ensemble (422), comme FastAPI.
 */
export const validateRequest = <S extends RequestSchemas>(
  req: Request,
  schemas: S,
): { params: Output<S['params']>; query: Output<S['query']>; body: Output<S['body']>; form: Output<S['form']> } => {
  const errors: FastApiValidationError[] = [];
  const result: Record<string, unknown> = {};

  const run = (key: keyof RequestSchemas, loc: Loc, schema: Shape | undefined, input: unknown) => {
    if (!schema) return;
    if (key === 'body' && input === undefined) {
      errors.push({ type: 'missing', loc: ['body'], msg: 'Field required', input: null });
      return;
    }
    const parsed = schema.safeParse(input, { reportInput: true });
    if (parsed.success) result[key] = parsed.data;
    else errors.push(...parsed.error.issues.map((issue) => toFastApiError(issue, loc, input)));
  };

  run('params', 'path', schemas.params, req.params);
  run('query', 'query', schemas.query, lastValues((req.query ?? {}) as Record<string, unknown>));
  run('form', 'form', schemas.form, withoutEmptyStrings((req.body ?? {}) as Record<string, unknown>));
  const emptyBody = req.headers['content-length'] === '0' && req.headers['transfer-encoding'] === undefined;
  run('body', 'body', schemas.body, emptyBody ? undefined : req.body);

  if (errors.length) throw new RequestValidationError(errors);
  return result as never;
};

/** Paramètres de chemin entiers (restaurant_id, order_id…). */
export const intParams = <const K extends string>(...names: K[]) =>
  z.object(Object.fromEntries(names.map((name) => [name, py.int()])) as { [P in K]: ReturnType<typeof py.int> });

export { z };
