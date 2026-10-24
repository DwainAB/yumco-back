/** Formats JSON des réponses (sérialisation Pydantic). */
import { DateTime } from 'luxon';
import { describe, expect, it } from 'vitest';
import { Prisma } from '../../src/generated/prisma/client.js';
import { date, datetime, decimalString, float, localDatetime, time } from '../../src/lib/serialize.js';

describe('serialization', () => {
  it('Decimal fields are strings with two decimals', () => {
    expect(decimalString(new Prisma.Decimal('12.5'))).toBe('12.50');
    expect(float(new Prisma.Decimal('12.50'))).toBe(12.5);
  });

  it('datetimes are ISO in UTC, without an empty fraction', () => {
    expect(datetime(new Date('2026-05-15T14:28:08.000Z'))).toBe('2026-05-15T14:28:08Z');
    expect(datetime(new Date('2026-05-15T14:28:08.123Z'))).toBe('2026-05-15T14:28:08.123Z');
  });

  it('local datetimes keep their offset', () => {
    expect(localDatetime(DateTime.fromISO('2026-10-24T12:15:00', { zone: 'Europe/Paris' }))).toBe('2026-10-24T12:15:00+02:00');
  });

  it('dates and times', () => {
    expect(date(new Date(Date.UTC(2026, 5, 15)))).toBe('2026-06-15');
    expect(time(new Date(Date.UTC(1970, 0, 1, 19, 30)))).toBe('19:30:00');
    expect(time(new Date(Date.UTC(1970, 0, 1, 10, 0, 0, 123)))).toBe('10:00:00.123000');
  });
});
