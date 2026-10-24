/**
 * Notifications push Expo vers les appareils de l'équipe du restaurant (notification_service.py).
 */
import { prisma } from '../../db/prisma.js';
import { logger } from '../../lib/logger.js';

const EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send';
const NOTIFIED_ROLES = ['owner', 'manager', 'staff'];

interface PushTarget {
  expo_push_token: string;
  platform: string | null;
}

interface ExpoMessage {
  to: string;
  sound: string;
  title: string;
  body: string;
  data?: Record<string, unknown>;
  channelId?: string;
}

/** Désactive les jetons signalés comme invalides par Expo (deactivate_push_tokens). */
export const deactivatePushTokens = async (tokens: string[]) => {
  if (!tokens.length) return;
  await prisma.userDevice.updateMany({ where: { expo_push_token: { in: tokens } }, data: { is_active: false } });
};

export const sendExpoPush = async (targets: (PushTarget | string)[], title: string, body: string, data?: Record<string, unknown>) => {
  if (!targets.length) return;

  const messages: ExpoMessage[] = [];
  for (const target of targets) {
    const token = typeof target === 'string' ? target : target.expo_push_token;
    const platform = typeof target === 'string' ? null : (target.platform ?? '').toLowerCase();
    if (!token || !token.startsWith('ExponentPushToken')) continue;
    const message: ExpoMessage = { to: token, sound: 'sound_notif.wav', title, body, ...(data ? { data } : {}) };
    if (platform === 'android') message.channelId = 'orders_v2';
    messages.push(message);
  }
  if (!messages.length) return;

  let tickets: { status?: string; details?: { error?: string } }[];
  try {
    const response = await fetch(EXPO_PUSH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(messages),
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) throw new Error(`Expo push API error (${response.status})`);
    const payload = (await response.json()) as { data?: typeof tickets };
    tickets = payload.data ?? [];
  } catch (error) {
    logger.warn({ error: String(error) }, '[notification_service] Erreur envoi push');
    return;
  }

  const invalidTokens = messages
    .filter((_, index) => tickets[index]?.status === 'error' && tickets[index]?.details?.error === 'DeviceNotRegistered')
    .map((message) => message.to);
  await deactivatePushTokens(invalidTokens);
};

const restaurantDevices = (restaurantId: number, preference: 'notify_orders' | 'notify_reservations') =>
  prisma.userDevice.findMany({
    where: {
      is_active: true,
      user: {
        [preference]: true,
        roles: { some: { restaurant_id: restaurantId, type: { in: NOTIFIED_ROLES } } },
      },
    },
    select: { expo_push_token: true, platform: true },
  });

export const notifyNewReservation = async (
  restaurantId: number,
  fullName: string,
  numberOfPeople: number,
  reservationDate: string,
  reservationTime: string,
) => {
  const devices = await restaurantDevices(restaurantId, 'notify_reservations');
  await sendExpoPush(
    devices,
    'Nouvelle réservation !',
    `${fullName} — ${numberOfPeople} pers. le ${reservationDate} à ${reservationTime}`,
    { type: 'new_reservation', restaurant_id: restaurantId },
  );
};

export const notifyNewOrder = async (restaurantId: number, orderNumber: string) => {
  const devices = await restaurantDevices(restaurantId, 'notify_orders');
  await sendExpoPush(devices, 'Nouvelle commande !', `La commande ${orderNumber} vient d'être passée.`, {
    type: 'new_order',
    restaurant_id: restaurantId,
  });
};
