/**
 * Outils communs aux statistiques (fonctions partagées de order_analytics_service.py).
 */
import { pyRound } from '../../lib/python.js';

export const WEEKDAY_LABELS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];

export const MONTH_LABELS: Record<number, string> = {
  1: 'Janvier',
  2: 'Fevrier',
  3: 'Mars',
  4: 'Avril',
  5: 'Mai',
  6: 'Juin',
  7: 'Juillet',
  8: 'Aout',
  9: 'Septembre',
  10: 'Octobre',
  11: 'Novembre',
  12: 'Decembre',
};

/** Valeur numérique renvoyée par PostgreSQL (numeric, bigint…) en nombre JS. */
export const toFloat = (value: unknown): number => (value === null || value === undefined ? 0 : Number(value));
export const toInt = (value: unknown): number => (value === null || value === undefined ? 0 : Math.trunc(Number(value)));

/** Évolution en % : 100 si on part de zéro, 0 si les deux sont nuls. */
export const percentageChange = (current: number, previous: number): number => {
  if (previous === 0) return current === 0 ? 0 : 100;
  return pyRound(((current - previous) / previous) * 100, 2);
};

export const monthLabel = (month: number, year: number) => `${MONTH_LABELS[month]} ${year}`;
export const dayLabel = (day: number, month: number, year: number) => `${day} ${MONTH_LABELS[month]} ${year}`;
