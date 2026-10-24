/**
 * Calculs d'argent, comme le Decimal de Python : `_money()` arrondit au centime (ROUND_HALF_UP).
 */
import { Prisma } from '../generated/prisma/client.js';

export type Decimal = Prisma.Decimal;
export const Decimal = Prisma.Decimal;

export const ZERO = new Decimal('0.00');

/**
 * Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).
 * Un nombre JS est converti par son écriture la plus courte, comme str(float) en Python.
 */
export const money = (value: Decimal | number | string): Decimal => toDecimal(value).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);

/** Conversion sans perte : un Decimal reste tel quel, un nombre passe par son écriture décimale. */
export const toDecimal = (value: Decimal | number | string): Decimal => (value instanceof Decimal ? value : new Decimal(String(value)));

export const maxDecimal = (a: Decimal, b: Decimal) => (a.greaterThanOrEqualTo(b) ? a : b);
export const minDecimal = (a: Decimal, b: Decimal) => (a.lessThanOrEqualTo(b) ? a : b);

/** Montant en centimes pour Stripe (_amount_to_cents). */
export const toCents = (amount: Decimal | number): number => toDecimal(amount).times(100).toDecimalPlaces(0, Decimal.ROUND_HALF_UP).toNumber();

/** Écriture `12.50` d'un montant (f"{float(value):.2f}"). */
export const formatAmount = (value: Decimal | number | null | undefined): string => Number(value ?? 0).toFixed(2);
