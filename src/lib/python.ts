/**
 * Équivalents exacts de fonctions Python utilisées dans les calculs (statistiques, scores).
 */

/** Écriture exacte d'un nombre flottant : value = mantissa × 2^exponent. */
const decompose = (value: number): { mantissa: bigint; exponent: number } => {
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, value);
  const bits = view.getBigUint64(0);
  const rawExponent = Number((bits >> 52n) & 0x7ffn);
  const fraction = bits & 0xfffffffffffffn;
  return rawExponent === 0
    ? { mantissa: fraction, exponent: -1074 }
    : { mantissa: fraction | (1n << 52n), exponent: rawExponent - 1075 };
};

/** Vrai si |value| × 10^digits tombe exactement à mi-chemin entre deux entiers. */
const isExactHalf = (value: number, digits: number): boolean => {
  const { mantissa, exponent } = decompose(Math.abs(value));
  if (exponent >= 0) return false;
  const scaled = mantissa * 10n ** BigInt(digits);
  const denominator = 1n << BigInt(-exponent);
  return scaled % denominator === denominator / 2n;
};

/**
 * round(value, digits) de Python : arrondi correct sur la valeur exacte, égalités vers le chiffre pair.
 * (toFixed arrondit aussi sur la valeur exacte, mais les égalités vers le haut.)
 */
export const pyRound = (value: number, digits = 0): number => {
  if (!Number.isFinite(value)) return value;
  const fixed = Number(value.toFixed(digits));
  if (!isExactHalf(value, digits)) return fixed;
  const factor = 10 ** digits;
  const lower = Math.sign(value) * Math.floor(Math.abs(value) * factor) / factor;
  const upper = Math.sign(value) * Math.ceil(Math.abs(value) * factor) / factor;
  const lowerIsEven = Math.round(Math.abs(lower) * factor) % 2 === 0;
  return lowerIsEven ? lower : upper;
};

/** Modulo Python (résultat du signe du diviseur) : pyMod(-1, 7) = 6. */
export const pyMod = (value: number, divisor: number) => ((value % divisor) + divisor) % divisor;
