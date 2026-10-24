/**
 * E-mails envoyés aux clients au fil de la commande (order_email_service.py).
 */
import { prisma } from '../../db/prisma.js';
import type { Customer, OrderItem, Restaurant, RestaurantConfig } from '../../generated/prisma/client.js';
import { buildBase64Attachment, sendEmail, sendEmailSafe } from '../email/email.service.js';
import { generateReceipt, receiptInclude, type ReceiptOrder } from './receipts.service.js';

export interface EmailOrder {
  id: number;
  order_number: string;
  type: string;
  amount_total: unknown;
  items: OrderItem[];
  customer: Customer | null;
}

const itemsHtml = (order: EmailOrder) =>
  order.items
    .map((item) =>
      item.parent_order_item_id !== null
        ? `<tr><td style='padding:2px 8px 2px 24px;color:#555;font-size:13px;'>› ${item.name}</td><td></td></tr>`
        : `<tr><td style='padding:4px 8px;'>${item.quantity}x ${item.name}</td><td style='padding:4px 8px;text-align:right;'>${Number(item.subtotal).toFixed(2)} €</td></tr>`,
    )
    .join('');

const baseTemplate = (restaurantName: string, title: string, bodyHtml: string, order: EmailOrder, ctaHtml = '') => `
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#222;">
      <div style="background:#111;padding:20px 24px;border-radius:8px 8px 0 0;">
        <h2 style="color:#fff;margin:0;">${restaurantName}</h2>
      </div>
      <div style="border:1px solid #ddd;border-top:none;padding:24px;border-radius:0 0 8px 8px;">
        <h3 style="margin-top:0;">${title}</h3>
        ${bodyHtml}
        ${ctaHtml}
        <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
        <p style="font-size:13px;font-weight:bold;margin-bottom:4px;">Récapitulatif de votre commande :</p>
        <table style="width:100%;font-size:14px;border-collapse:collapse;">
          ${itemsHtml(order)}
          <tr style="border-top:1px solid #eee;">
            <td style="padding:8px;font-weight:bold;">Total</td>
            <td style="padding:8px;text-align:right;font-weight:bold;">${Number(order.amount_total).toFixed(2)} €</td>
          </tr>
        </table>
        <p style="font-size:11px;color:#aaa;margin-top:32px;text-align:center;">Propulsé par Yumco</p>
      </div>
    </div>
    `;

export const sendOrderConfirmed = async (order: EmailOrder, restaurant: Restaurant) => {
  if (!order.customer?.email) return;
  const body = `
    <p>Bonjour <strong>${order.customer.first_name}</strong>,</p>
    <p>Nous avons bien reçu votre commande <strong>${order.order_number}</strong> et nous la traitons dès maintenant.</p>
    <p>Nous vous tiendrons informé de l'avancement de votre commande.</p>
    <p>Merci pour votre confiance !</p>
    <p><em>L'équipe ${restaurant.name}</em></p>
    `;
  await sendEmail({
    to: order.customer.email,
    subject: `${restaurant.name} – Commande ${order.order_number} confirmée`,
    body: baseTemplate(restaurant.name, 'Commande reçue ✓', body, order),
  });
};

export const sendOrderPreparing = async (
  order: EmailOrder,
  restaurant: Restaurant & { config?: RestaurantConfig | null },
  preparationTime?: number | null,
) => {
  if (!order.customer?.email) return;
  let minutes = preparationTime;
  if (minutes == null) {
    const config = restaurant.config ?? (await prisma.restaurantConfig.findUnique({ where: { restaurant_id: restaurant.id } }));
    minutes = config?.preparation_time ?? null;
  }
  const timeLine = minutes ? `<p>Temps de préparation estimé : <strong>${minutes >= 60 ? '1h' : `${minutes} minutes`}</strong></p>` : '';
  const body = `
    <p>Bonjour <strong>${order.customer.first_name}</strong>,</p>
    <p>Bonne nouvelle ! Votre commande <strong>${order.order_number}</strong> est actuellement en cours de préparation.</p>
    ${timeLine}
    <p>Nous faisons tout pour vous la préparer dans les meilleurs délais.</p>
    <p><em>L'équipe ${restaurant.name}</em></p>
    `;
  await sendEmail({
    to: order.customer.email,
    subject: `${restaurant.name} – Commande ${order.order_number} en préparation`,
    body: baseTemplate(restaurant.name, 'Votre commande est en préparation 👨‍🍳', body, order),
  });
};

export const sendOrderCompleted = async (order: EmailOrder, restaurant: Restaurant) => {
  if (!order.customer?.email) return;
  const [action, subtitle] =
    order.type === 'pickup'
      ? ['Vous pouvez dès à présent venir récupérer votre commande à notre adresse.', 'Votre commande est prête à être récupérée 🛍️']
      : ['Votre commande est en route et sera livrée chez vous très prochainement.', 'Votre commande est en route 🚗'];
  const body = `
    <p>Bonjour <strong>${order.customer.first_name}</strong>,</p>
    <p>Votre commande <strong>${order.order_number}</strong> est prête !</p>
    <p>${action}</p>
    <p>Merci et à bientôt !</p>
    <p><em>L'équipe ${restaurant.name}</em></p>
    `;
  await sendEmail({
    to: order.customer.email,
    subject: `${restaurant.name} – Commande ${order.order_number} prête`,
    body: baseTemplate(restaurant.name, subtitle, body, order),
  });
};

export const sendOrderCancelled = async (order: EmailOrder, restaurant: Restaurant) => {
  if (!order.customer?.email) return;
  const body = `
    <p>Bonjour <strong>${order.customer.first_name}</strong>,</p>
    <p>Nous sommes navrés de vous informer que votre commande <strong>${order.order_number}</strong> a été annulée.</p>
    <p>Si vous avez des questions, n'hésitez pas à nous contacter directement.</p>
    <p>Nous espérons vous revoir très prochainement.</p>
    <p><em>L'équipe ${restaurant.name}</em></p>
    `;
  await sendEmail({
    to: order.customer.email,
    subject: `${restaurant.name} – Commande ${order.order_number} annulée`,
    body: baseTemplate(restaurant.name, 'Commande annulée', body, order),
  });
};

export const sendOrderReceipt = async (order: ReceiptOrder, restaurant: Restaurant, toEmail: string) => {
  const customerName = order.customer ? order.customer.first_name : 'client';
  const body = `
    <p>Bonjour <strong>${customerName}</strong>,</p>
    <p>Veuillez trouver en pièce jointe le reçu de votre commande <strong>${order.order_number}</strong>.</p>
    <p><em>L'équipe ${restaurant.name}</em></p>
    `;
  const pdf = await generateReceipt(order, restaurant);
  await sendEmail({
    to: toEmail,
    subject: `${restaurant.name} – Reçu de la commande ${order.order_number}`,
    body: baseTemplate(restaurant.name, 'Votre reçu de commande', body, order),
    attachments: [buildBase64Attachment(`ticket_${order.order_number.replaceAll('#', '')}.pdf`, pdf)],
  });
};

/** Demande d'avis Google 24 h après la commande ; renvoie false si l'e-mail n'est pas parti. */
export const sendReviewFollowupEmail = async (order: EmailOrder, restaurant: Restaurant, toEmail: string, customerFirstName?: string | null) => {
  const reviewUrl = restaurant.google_review_url;
  if (!reviewUrl) return false;
  const customerName = customerFirstName || (order.customer ? order.customer.first_name : 'client');
  const body = `
    <p>Bonjour <strong>${customerName}</strong>,</p>
    <p>Qu'avez-vous pensé de votre expérience chez <strong>${restaurant.name}</strong> ?</p>
    <p>Votre avis compte beaucoup pour nous et aide d'autres clients à nous découvrir.</p>
    <p>Merci pour votre confiance et à bientôt.</p>
    <p><em>L'équipe ${restaurant.name}</em></p>
    `;
  const cta = `
    <div style="margin:24px 0;text-align:center;">
      <a href="${reviewUrl}" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:12px 20px;border-radius:999px;font-weight:bold;">
        Laisser un avis sur Google
      </a>
    </div>
    `;
  return sendEmailSafe({
    to: toEmail,
    subject: `${restaurant.name} – Qu'avez-vous pensé de votre expérience ?`,
    body: baseTemplate(restaurant.name, 'Votre avis nous intéresse', body, order, cta),
  });
};

/** Commande rechargée avec ses articles et son client, pour une tâche lancée après la réponse. */
export const loadEmailOrder = (orderId: number) => prisma.order.findUnique({ where: { id: orderId }, include: receiptInclude });
