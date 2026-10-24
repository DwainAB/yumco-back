/**
 * Fuseaux horaires (zoneinfo en Python) avec Luxon.
 */
import { DateTime } from 'luxon';

export const DEFAULT_TIMEZONE = 'Europe/Paris';

/** Fuseau du restaurant ; une valeur inconnue lève une erreur comme ZoneInfo. */
export const zoneOf = (timezone: string | null | undefined): string => {
  const zone = timezone || DEFAULT_TIMEZONE;
  if (!DateTime.now().setZone(zone).isValid) throw new Error(`No time zone found with key ${zone}`);
  return zone;
};

export const nowIn = (zone: string) => DateTime.now().setZone(zone);

export const toZone = (value: Date, zone: string) => DateTime.fromJSDate(value).setZone(zone);

/** Bornes des périodes en UTC (_period_bounds) : mois courant, précédent, suivant, années. */
export const periodBounds = (nowLocal: DateTime) => {
  const monthStart = nowLocal.startOf('month');
  const yearStart = nowLocal.startOf('year');
  return {
    month_start_utc: monthStart.toJSDate(),
    previous_month_start_utc: monthStart.minus({ months: 1 }).toJSDate(),
    next_month_start_utc: monthStart.plus({ months: 1 }).toJSDate(),
    current_year_start_utc: yearStart.toJSDate(),
    previous_year_start_utc: yearStart.minus({ years: 1 }).toJSDate(),
    next_year_start_utc: yearStart.plus({ years: 1 }).toJSDate(),
  };
};

export type PeriodBounds = ReturnType<typeof periodBounds>;

/** Début d'une journée locale ('YYYY-MM-DD') en UTC. */
export const localDayStart = (isoDate: string, zone: string) => DateTime.fromISO(isoDate, { zone }).startOf('day');
