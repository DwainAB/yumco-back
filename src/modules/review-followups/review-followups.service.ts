/**
 * Demandes d'avis Google envoyées 24 h après une commande terminée (review_followup_service.py).
 */
import { prisma } from '../../db/prisma.js';
import type { Restaurant } from '../../generated/prisma/client.js';
import { sendReviewFollowupEmail } from '../orders/order-emails.service.js';
import { receiptInclude } from '../orders/receipts.service.js';

const REVIEW_FOLLOWUP_DELAY_MS = 24 * 3600 * 1000;

interface CompletedOrder {
  id: number;
  completed_at: Date | null;
  customer: { email: string | null; first_name: string } | null;
}

/** Programme la demande d'avis si la commande est terminée, que le client a un e-mail et que le restaurant a un lien d'avis. */
export const scheduleReviewFollowup = async (order: CompletedOrder, restaurant: Restaurant) => {
  if (!order.completed_at || !order.customer?.email || !restaurant.google_review_url) return null;
  const existing = await prisma.reviewFollowup.findFirst({ where: { order_id: order.id } });
  if (existing) return existing;
  return prisma.reviewFollowup.create({
    data: {
      order_id: order.id,
      restaurant_id: restaurant.id,
      customer_email: order.customer.email,
      customer_first_name: order.customer.first_name,
      status: 'pending',
      send_at: new Date(order.completed_at.getTime() + REVIEW_FOLLOWUP_DELAY_MS),
    },
  });
};

/** Envoie les demandes arrivées à échéance (appelé par une tâche planifiée). */
export const processDueReviewFollowups = async (limit = 100) => {
  const now = new Date();
  const due = await prisma.reviewFollowup.findMany({
    where: { status: 'pending', send_at: { lte: now } },
    orderBy: { send_at: 'asc' },
    take: limit,
  });

  let sent = 0;
  let failed = 0;
  let cancelled = 0;
  for (const followup of due) {
    const order = await prisma.order.findUnique({ where: { id: followup.order_id }, include: receiptInclude });
    const restaurant = await prisma.restaurant.findUnique({ where: { id: followup.restaurant_id } });

    if (!order || !restaurant || !restaurant.google_review_url) {
      await prisma.reviewFollowup.update({
        where: { id: followup.id },
        data: { status: 'cancelled', last_error: 'Missing order, restaurant, or google review url' },
      });
      cancelled += 1;
      continue;
    }

    const ok = await sendReviewFollowupEmail(order, restaurant, followup.customer_email, followup.customer_first_name);
    await prisma.reviewFollowup.update({
      where: { id: followup.id },
      data: ok ? { status: 'sent', sent_at: now, last_error: null } : { status: 'failed', last_error: 'Email send failed' },
    });
    if (ok) sent += 1;
    else failed += 1;
  }
  return { processed: due.length, sent, failed, cancelled };
};
