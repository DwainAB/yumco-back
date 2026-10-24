/**
 * Créneaux de retrait ou de livraison d'une journée (get_order_slots dans routes/order.py).
 */
import { DateTime } from 'luxon';
import { prisma } from '../../db/prisma.js';
import type { Restaurant } from '../../generated/prisma/client.js';
import { localDatetime } from '../../lib/serialize.js';
import { zoneOf } from '../../lib/time.js';

const SLOT_MINUTES = 15;

/** Arrondit au quart d'heure supérieur puis remet les secondes à zéro, exactement comme le Python. */
const roundUpToSlot = (value: DateTime) => {
  const remainder = value.minute % SLOT_MINUTES;
  const rounded = remainder ? value.plus({ minutes: SLOT_MINUTES - remainder }) : value;
  return rounded.set({ second: 0, millisecond: 0 });
};

export const getOrderSlots = async (restaurant: Restaurant, type: 'pickup' | 'delivery', isoDate: string | null) => {
  const zone = zoneOf(restaurant.timezone);
  const now = DateTime.now().setZone(zone);
  const targetDate = isoDate ?? now.toISODate()!;
  // Lundi = 0 … dimanche = 6, comme date.weekday().
  const weekday = DateTime.fromISO(targetDate).weekday - 1;

  const hours = await prisma.openingHours.findFirst({ where: { restaurant_id: restaurant.id, day: weekday }, orderBy: { id: 'asc' } });
  if (!hours || hours.is_closed) return { asap: false, slots: [] as string[] };

  const windows: [DateTime, DateTime][] = [];
  for (const [open, close] of [
    [hours.lunch_open, hours.lunch_close],
    [hours.dinner_open, hours.dinner_close],
  ]) {
    if (open && close) {
      const openAt = DateTime.fromISO(`${targetDate}T${open}`, { zone });
      const closeAt = DateTime.fromISO(`${targetDate}T${close}`, { zone });
      if (!openAt.isValid || !closeAt.isValid) throw new Error(`Invalid isoformat string: '${targetDate}T${open}'`);
      windows.push([openAt, closeAt]);
    }
  }
  if (!windows.length) return { asap: false, slots: [] as string[] };

  // Livraison : dernier créneau 30 min avant la fermeture. Délai minimum : 30 min à partir de maintenant.
  const cutoffMinutes = type === 'delivery' ? 30 : 0;
  const earliest = roundUpToSlot(now.plus({ minutes: 30 }));

  const slots: string[] = [];
  for (const [openAt, closeAt] of windows) {
    const lastSlot = closeAt.minus({ minutes: cutoffMinutes });
    let cursor = roundUpToSlot(openAt > earliest ? openAt : earliest);
    while (cursor <= lastSlot) {
      slots.push(localDatetime(cursor));
      cursor = cursor.plus({ minutes: SLOT_MINUTES });
    }
  }

  const asap = windows.some(([openAt, closeAt]) => openAt <= now && now <= closeAt);
  return { asap, slots };
};
