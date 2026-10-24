/** Équivalents des fonctions Python utilisées dans les calculs. */
import { describe, expect, it } from 'vitest';
import { money, toCents } from '../../src/lib/money.js';
import { pyMod, pyRound } from '../../src/lib/python.js';

describe('pyRound (round() de Python)', () => {
  it.each([
    [2.675, 2, 2.67], // 2.675 vaut en réalité 2.67499999…
    [0.125, 2, 0.12], // égalité exacte : chiffre pair
    [0.375, 2, 0.38],
    [1.005, 2, 1],
    [12.3456, 2, 12.35],
    [-0.125, 2, -0.12],
    [2.5, 0, 2],
    [3.5, 0, 4],
    [1.45553, 2, 1.46],
    [33.333333, 2, 33.33],
  ])('round(%s, %s) = %s', (value, digits, expected) => {
    expect(pyRound(value, digits)).toBe(expected);
  });
});

describe('pyMod', () => {
  it('keeps the sign of the divisor like Python', () => {
    expect(pyMod(-1, 7)).toBe(6);
    expect(pyMod(8, 7)).toBe(1);
  });
});

describe('money (Decimal quantize ROUND_HALF_UP)', () => {
  it('rounds half up on the decimal writing of the float', () => {
    expect(money(12.3 * 3).toFixed(2)).toBe('36.90');
    expect(money(2.675).toFixed(2)).toBe('2.68'); // str(2.675) = '2.675' → 2.68, comme Decimal(str(x))
    expect(money('10.005').toFixed(2)).toBe('10.01');
  });

  it('converts to cents for Stripe', () => {
    expect(toCents(money(19.99))).toBe(1999);
    expect(toCents(0.105)).toBe(11);
  });
});
