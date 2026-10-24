/** Règles de validation de Pydantic reproduites avec Zod. */
import type { Request } from 'express';
import { describe, expect, it } from 'vitest';
import { serializeOrderCreate, OrderCreate } from '../../src/modules/orders/orders.schemas.js';
import { RestaurantUpdate } from '../../src/modules/restaurants/restaurants.schemas.js';
import { intParams, py, RequestValidationError, validateRequest, z } from '../../src/lib/validation.js';

const request = (parts: Partial<Request>) => ({ params: {}, query: {}, headers: {}, ...parts }) as Request;

const errorsOf = (fn: () => unknown) => {
  try {
    fn();
  } catch (error) {
    if (error instanceof RequestValidationError) return error.errors;
    throw error;
  }
  throw new Error('no validation error');
};

describe('conversions', () => {
  const schema = z.object({ count: py.int(), flag: py.bool(), price: py.decimal(), when: py.datetime() });

  it('accepts the same inputs as Pydantic (lax mode)', () => {
    const data = schema.parse({ count: '5', flag: 'yes', price: 12.3, when: '2026-01-01 10:00' });
    expect(data.count).toBe(5);
    expect(data.flag).toBe(true);
    expect(data.price.toString()).toBe('12.3');
    expect(data.when.toISOString()).toBe('2026-01-01T10:00:00.000Z');
  });

  it('reads timezones and unix timestamps', () => {
    expect(schema.shape.when.parse('2026-10-25T12:30:00+02:00').toISOString()).toBe('2026-10-25T10:30:00.000Z');
    expect(schema.shape.when.parse(1_700_000_000).toISOString()).toBe('2023-11-14T22:13:20.000Z');
  });

  it('normalizes e-mail addresses like email-validator', () => {
    expect(py.email().parse('Jean.Dupont@GMAIL.COM')).toBe('Jean.Dupont@gmail.com');
  });

  it('normalizes URLs like HttpUrl', () => {
    expect(py.httpUrl().parse('https://example.com')).toBe('https://example.com/');
  });
});

describe('errors in the FastAPI format', () => {
  it('reports every error at once, with loc, msg, input and ctx', () => {
    const errors = errorsOf(() =>
      validateRequest(request({ params: { id: 'abc' }, body: { email: 'nope' } }), {
        params: intParams('id'),
        body: z.object({ email: py.email(), name: py.str() }),
      }),
    );
    expect(errors).toEqual([
      { type: 'int_parsing', loc: ['path', 'id'], msg: 'Input should be a valid integer, unable to parse string as an integer', input: 'abc' },
      {
        type: 'value_error',
        loc: ['body', 'email'],
        msg: 'value is not a valid email address: An email address must have an @-sign.',
        input: 'nope',
        ctx: { reason: 'An email address must have an @-sign.' },
      },
      { type: 'missing', loc: ['body', 'name'], msg: 'Field required', input: { email: 'nope' } },
    ]);
  });

  it('a missing body', () => {
    expect(errorsOf(() => validateRequest(request({ body: undefined }), { body: z.object({ a: py.str() }) }))).toEqual([
      { type: 'missing', loc: ['body'], msg: 'Field required', input: null },
    ]);
  });

  it('date messages from speedate', () => {
    const errors = errorsOf(() => validateRequest(request({ body: { day: '2026-13-01', at: '25:00' } }), { body: z.object({ day: py.date(), at: py.time() }) }));
    expect(errors.map((error) => error.msg)).toEqual([
      'Input should be a valid date or datetime, month value is outside expected range of 1-12',
      'Input should be in a valid time format, hour value is outside expected range of 0-23',
    ]);
  });
});

describe('partial updates (exclude_unset)', () => {
  it('keeps absent fields absent and explicit nulls as null', () => {
    const data = RestaurantUpdate.parse({ name: 'X', phone: null, unknown: 1 });
    expect(Object.keys(data).filter((key) => data[key as keyof typeof data] !== undefined)).toEqual(['name', 'phone']);
    expect(data.phone).toBeNull();
  });
});

describe('pending online orders', () => {
  it('stores the order in the same JSON as model_dump_json()', () => {
    const order = OrderCreate.parse({
      type: 'pickup',
      customer: { first_name: 'A', last_name: 'B', email: 'A@B.FR' },
      items: [{ product_id: 3 }],
      requested_time: '2026-10-25T12:30:00+02:00',
    });
    expect(JSON.parse(serializeOrderCreate(order))).toEqual({
      type: 'pickup',
      promo_code: null,
      comment: null,
      requested_time: '2026-10-25T10:30:00Z',
      table_id: null,
      address: null,
      customer: { first_name: 'A', last_name: 'B', email: 'A@b.fr', phone: null },
      items: [{ product_id: 3, menu_id: null, all_you_can_eat_id: null, quantity: 1, comment: null, selected_options: [] }],
    });
  });
});
