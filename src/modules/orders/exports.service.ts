/**
 * Export des commandes terminées en CSV ou en récapitulatif PDF (order_export_service.py).
 */
import { DateTime } from 'luxon';
import { prisma } from '../../db/prisma.js';
import type { Restaurant } from '../../generated/prisma/client.js';
import { formatAmount } from '../../lib/money.js';
import { pyRound } from '../../lib/python.js';
import { toZone, zoneOf } from '../../lib/time.js';
import { Canvas, MM, receiptInclude, type ReceiptOrder } from './receipts.service.js';

const ORDER_TYPE_LABELS: Record<string, string> = { delivery: 'Livraison', pickup: 'A emporter', onsite: 'Sur place' };
const PAYMENT_STATUS_LABELS: Record<string, string> = { unpaid: 'Non paye', awaiting_payment: 'En attente', paid: 'Paye', refunded: 'Rembourse' };

export class ExportPeriodError extends Error {}

/** Période demandée, en bornes UTC, et son libellé (_localize_datetime_range). */
const localizeRange = (zone: string, startDate: string | null, endDate: string | null, month: number | null, year: number | null) => {
  if (startDate && endDate && startDate > endDate) throw new ExportPeriodError('date_from must be before or equal to date_to');
  if ((startDate === null) !== (endDate === null)) throw new ExportPeriodError('date_from and date_to must be provided together');
  if (month !== null && year === null) throw new ExportPeriodError('year is required when month is provided');
  if (month === null && year !== null) throw new ExportPeriodError('month is required when year is provided');

  if (startDate && endDate) {
    const start = DateTime.fromISO(startDate, { zone }).startOf('day');
    const end = DateTime.fromISO(endDate, { zone }).startOf('day').plus({ days: 1 });
    const label = `${DateTime.fromISO(startDate).toFormat('dd/MM/yyyy')} - ${DateTime.fromISO(endDate).toFormat('dd/MM/yyyy')}`;
    return { start: start.toJSDate(), end: end.toJSDate(), label };
  }
  if (month !== null && year !== null) {
    const start = DateTime.fromObject({ year, month, day: 1 }, { zone });
    return { start: start.toJSDate(), end: start.plus({ months: 1 }).toJSDate(), label: start.toFormat('MM/yyyy') };
  }
  return { start: null, end: null, label: 'toutes_periodes' };
};

export const getExportOrders = async (
  restaurantId: number,
  filters: { startDate: string | null; endDate: string | null; month: number | null; year: number | null },
) => {
  const restaurant = await prisma.restaurant.findUnique({ where: { id: restaurantId } });
  if (!restaurant) return null;
  const zone = zoneOf(restaurant.timezone);
  const { start, end, label } = localizeRange(zone, filters.startDate, filters.endDate, filters.month, filters.year);

  const orders = await prisma.order.findMany({
    where: {
      restaurant_id: restaurantId,
      status: 'completed',
      is_draft: false,
      ...(start || end ? { created_at: { ...(start ? { gte: start } : {}), ...(end ? { lt: end } : {}) } } : {}),
    },
    include: receiptInclude,
    orderBy: [{ created_at: 'asc' }, { id: 'asc' }],
  });
  return { restaurant, orders, zone, periodLabel: label };
};

const formatLocal = (value: Date | null, zone: string) => (value ? toZone(value, zone).toFormat('dd/MM/yyyy HH:mm') : '');

/** « 2x Burger (Frites, Coca) | 1x Tiramisu » : lignes principales et leurs options. */
const itemsText = (order: ReceiptOrder) => {
  const optionsByParent = new Map<number, string[]>();
  for (const item of order.items) {
    if (item.parent_order_item_id === null) continue;
    optionsByParent.set(item.parent_order_item_id, [...(optionsByParent.get(item.parent_order_item_id) ?? []), item.name]);
  }
  return order.items
    .filter((item) => item.parent_order_item_id === null)
    .map((item) => {
      const options = optionsByParent.get(item.id);
      const label = `${item.quantity}x ${item.name}`;
      return options?.length ? `${label} (${options.join(', ')})` : label;
    })
    .join(' | ');
};

const customerName = (order: ReceiptOrder) => (order.customer ? `${order.customer.first_name} ${order.customer.last_name}`.trim() : '');

export const buildExportSummary = (orders: ReceiptOrder[]) => {
  const summary = {
    orders_count: orders.length,
    amount_total: 0,
    items_subtotal: 0,
    delivery_fee_total: 0,
    discount_total: 0,
    average_basket: 0,
    delivery_count: 0,
    pickup_count: 0,
    onsite_count: 0,
  };
  for (const order of orders) {
    summary.amount_total += Number(order.amount_total ?? 0);
    summary.items_subtotal += Number(order.items_subtotal ?? 0);
    summary.delivery_fee_total += Number(order.delivery_fee ?? 0);
    summary.discount_total += Number(order.discount_amount ?? 0);
    if (order.type === 'delivery') summary.delivery_count += 1;
    else if (order.type === 'pickup') summary.pickup_count += 1;
    else if (order.type === 'onsite') summary.onsite_count += 1;
  }
  if (summary.orders_count > 0) summary.average_basket = summary.amount_total / summary.orders_count;
  for (const key of ['amount_total', 'items_subtotal', 'delivery_fee_total', 'discount_total', 'average_basket'] as const) {
    summary[key] = pyRound(summary[key], 2);
  }
  return summary;
};

/** Champ CSV comme le module csv de Python (QUOTE_MINIMAL). */
const csvField = (value: string) => (/[;"\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value);

const csvRow = (fields: string[]) => (fields.length === 1 && fields[0] === '' ? '""' : fields.map(csvField).join(';'));

export const generateOrdersCsv = (restaurant: Restaurant, orders: ReceiptOrder[], zone: string, periodLabel: string): Buffer => {
  const rows: string[][] = [
    ['Restaurant', restaurant.name],
    ['Periode', periodLabel],
    [],
    [
      'Numero',
      'Date commande',
      'Date completion',
      'Type',
      'Statut',
      'Paiement',
      'Sous-total articles',
      'Remise',
      'Frais livraison',
      'Total',
      'Client',
      'Telephone',
      'Email',
      'Adresse / Table',
      'Articles',
      'Commentaire',
    ],
  ];
  for (const order of orders) {
    let addressOrTable = '';
    if (order.address) addressOrTable = `${order.address.street}, ${order.address.postal_code} ${order.address.city}`;
    else if (order.table_id !== null) addressOrTable = `Table ${order.table_id}`;
    const payment = order.payment_status ?? '';
    rows.push([
      order.order_number,
      formatLocal(order.created_at, zone),
      formatLocal(order.completed_at, zone),
      ORDER_TYPE_LABELS[order.type] ?? order.type,
      order.status ?? '',
      PAYMENT_STATUS_LABELS[payment] ?? payment,
      formatAmount(order.items_subtotal),
      formatAmount(order.discount_amount),
      formatAmount(order.delivery_fee),
      formatAmount(order.amount_total),
      customerName(order),
      order.customer?.phone ?? '',
      order.customer?.email ?? '',
      addressOrTable,
      itemsText(order),
      order.comment ?? '',
    ]);
  }
  const content = rows.map((row) => `${csvRow(row)}\r\n`).join('');
  return Buffer.from(`\uFEFF${content}`, 'utf8');
};

export const generateOrdersSummaryPdf = (restaurant: Restaurant, orders: ReceiptOrder[], zone: string, periodLabel: string) => {
  const summary = buildExportSummary(orders);
  const pageWidth = 595.2755905511812;
  const pageHeight = 841.8897637795275;
  const c = new Canvas(pageWidth, pageHeight);
  const leftMargin = 18 * MM;
  const rightMargin = pageWidth - 18 * MM;
  let y = pageHeight - 20 * MM;

  const drawText = (text: string, { size = 10, bold = false, color = '#000000', gap = 6 } = {}) => {
    c.setFillColor(color);
    c.setFont(bold ? 'Helvetica-Bold' : 'Helvetica', size);
    c.drawString(leftMargin, y, text);
    y -= gap * MM;
  };

  drawText(restaurant.name, { size: 18, bold: true, gap: 4 });
  drawText('Recapitulatif des commandes', { size: 13, bold: true, gap: 3 });
  drawText(`Periode : ${periodLabel}`, { size: 10, color: '#555555', gap: 8 });

  const metrics = [
    `Commandes completes : ${summary.orders_count}`,
    `Chiffre d'affaires : ${summary.amount_total.toFixed(2)} EUR`,
    `Panier moyen : ${summary.average_basket.toFixed(2)} EUR`,
    `Remises : ${summary.discount_total.toFixed(2)} EUR`,
    `Frais de livraison : ${summary.delivery_fee_total.toFixed(2)} EUR`,
    `Canaux : livraison ${summary.delivery_count} | a emporter ${summary.pickup_count} | sur place ${summary.onsite_count}`,
  ];
  for (const metric of metrics) drawText(metric, { size: 10, gap: 4 });

  y -= 2 * MM;
  c.line(leftMargin, y, rightMargin, y, { color: '#D8D8D8' });
  y -= 8 * MM;

  const headers = ['Numero', 'Date', 'Type', 'Client', 'Total'];
  const positions = [leftMargin, 52 * MM, 92 * MM, 122 * MM, 178 * MM];
  c.setFillColor('#000000');
  c.setFont('Helvetica-Bold', 9);
  headers.forEach((header, index) => c.drawString(positions[index], y, header));
  y -= 5 * MM;
  c.line(leftMargin, y, rightMargin, y, { color: '#E6E6E6' });
  y -= 5 * MM;

  c.setFont('Helvetica', 8);
  for (const order of orders) {
    if (y <= 20 * MM) {
      c.showPage();
      y = pageHeight - 20 * MM;
      c.setFont('Helvetica', 8);
    }
    const values = [
      order.order_number,
      formatLocal(order.created_at, zone),
      ORDER_TYPE_LABELS[order.type] ?? order.type,
      customerName(order).slice(0, 26),
      `${Number(order.amount_total ?? 0).toFixed(2)} EUR`,
    ];
    values.forEach((value, index) => c.drawString(positions[index], y, value));
    y -= 4.5 * MM;

    const text = itemsText(order);
    if (text) {
      c.setFillColor('#555555');
      c.drawString(leftMargin + 4 * MM, y, text.slice(0, 110));
      c.setFillColor('#000000');
      y -= 4.5 * MM;
    }
    c.line(leftMargin, y, rightMargin, y, { color: '#F0F0F0' });
    y -= 4 * MM;
  }
  return c.save();
};
