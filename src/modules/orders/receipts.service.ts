/**
 * Tickets PDF au format imprimante thermique 80 mm (receipt_service.py) : ticket de commande et ticket de table.
 * Les positions sont celles de reportlab (origine en bas à gauche), converties pour pdfkit (origine en haut).
 */
import PDFDocument from 'pdfkit';
import type { Prisma, Restaurant, Table } from '../../generated/prisma/client.js';
import { toZone, zoneOf } from '../../lib/time.js';

export const MM = 72 / 25.4;

export const receiptInclude = {
  items: { orderBy: { id: 'asc' } },
  customer: true,
  address: true,
} as const satisfies Prisma.OrderInclude;

export type ReceiptOrder = Prisma.OrderGetPayload<{ include: typeof receiptInclude }>;

type Font = 'Helvetica' | 'Helvetica-Bold' | 'Helvetica-Oblique';

/** Canevas « à la reportlab » : y compté depuis le bas de la page, texte posé sur sa ligne de base. */
export class Canvas {
  readonly doc: PDFKit.PDFDocument;
  private readonly chunks: Buffer[] = [];
  private readonly done: Promise<Buffer>;

  constructor(
    readonly width: number,
    readonly height: number,
  ) {
    this.doc = new PDFDocument({ size: [width, height], margin: 0 });
    this.done = new Promise((resolve) => {
      this.doc.on('data', (chunk: Buffer) => this.chunks.push(chunk));
      this.doc.on('end', () => resolve(Buffer.concat(this.chunks)));
    });
  }

  setFont(font: Font, size: number) {
    this.doc.font(font).fontSize(size);
  }

  setFillColor(color: string) {
    this.doc.fillColor(color);
  }

  stringWidth(text: string, font: Font, size: number) {
    return this.doc.font(font).fontSize(size).widthOfString(text);
  }

  drawString(x: number, y: number, text: string) {
    this.doc.text(text, x, this.height - y, { lineBreak: false, baseline: 'alphabetic' });
  }

  drawCentredString(x: number, y: number, text: string) {
    this.drawString(x - this.doc.widthOfString(text) / 2, y, text);
  }

  drawRightString(x: number, y: number, text: string) {
    this.drawString(x - this.doc.widthOfString(text), y, text);
  }

  line(x1: number, y1: number, x2: number, y2: number, { dash = false, color = 'black' } = {}) {
    this.doc.save();
    if (dash) this.doc.dash(2, { space: 2 });
    this.doc.strokeColor(color).moveTo(x1, this.height - y1).lineTo(x2, this.height - y2).stroke();
    this.doc.restore();
  }

  showPage() {
    this.doc.addPage({ size: [this.width, this.height], margin: 0 });
  }

  save(): Promise<Buffer> {
    this.doc.end();
    return this.done;
  }
}

const TYPE_LABELS: Record<string, string> = { delivery: 'Livraison', pickup: 'À emporter', onsite: 'Sur place' };
const PAYMENT_LABELS: Record<string, string> = {
  unpaid: 'Non payé',
  awaiting_payment: 'En attente de paiement',
  paid: 'Payé',
  refunded: 'Remboursé',
};

/** Date au format « 24/10/2026 à 12:30 », à l'heure du restaurant (le Python l'affichait en UTC). */
const localStamp = (value: Date, restaurant: Restaurant) => toZone(value, zoneOf(restaurant.timezone)).toFormat("dd/MM/yyyy 'à' HH:mm");

const amount = (value: unknown) => `${Number(value).toFixed(2)} €`;

export const generateReceipt = (order: ReceiptOrder, restaurant: Restaurant): Promise<Buffer> => {
  const width = 80 * MM;
  const estimatedHeight = ((40 + 30 + order.items.length * 14 + 30 + 40 + 20) * MM) / 10;
  const height = Math.max(estimatedHeight, 80 * MM);
  const c = new Canvas(width, height);
  let y = height - 6 * MM;

  const line = (text: string, { size = 8, bold = false, center = false, gap = 4 } = {}) => {
    c.setFont(bold ? 'Helvetica-Bold' : 'Helvetica', size);
    if (center) c.drawCentredString(width / 2, y, text);
    else c.drawString(5 * MM, y, text);
    y -= gap * MM;
  };

  const separator = (dash = false) => {
    c.line(5 * MM, y, width - 5 * MM, y, { dash });
    y -= 5 * MM;
  };

  line(restaurant.name, { size: 12, bold: true, center: true, gap: 4 });
  line(order.order_number, { bold: true, size: 10, center: true, gap: 5 });
  line(`Date : ${localStamp(order.created_at!, restaurant)}`, { size: 8, center: true, gap: 3 });
  if (order.requested_time) line(`Pour : ${localStamp(order.requested_time, restaurant)}`, { size: 8, center: true, gap: 3 });
  line(TYPE_LABELS[order.type] ?? order.type, { size: 9, center: true, gap: 4 });
  if (order.type === 'onsite' && order.table_id) line(`Table ${order.table_id}`, { size: 8, center: true, gap: 3 });

  separator();

  for (const item of order.items) {
    if (item.parent_order_item_id !== null) {
      const unitPrice = Number(item.unit_price);
      c.setFont('Helvetica', 7);
      c.drawString(9 * MM, y, `› ${item.name}`);
      if (unitPrice > 0) c.drawRightString(width - 5 * MM, y, amount(unitPrice));
      y -= 3.5 * MM;
    } else {
      c.setFont('Helvetica-Bold', 8);
      c.drawString(5 * MM, y, `${item.quantity}x ${item.name}`);
      c.drawRightString(width - 5 * MM, y, amount(item.subtotal));
      y -= 4 * MM;
      if (item.quantity > 1) {
        c.setFont('Helvetica', 7);
        c.drawString(9 * MM, y, `${amount(item.unit_price)} / unité`);
        y -= 3.5 * MM;
      }
    }
    if (item.comment) {
      c.setFont('Helvetica-Oblique', 7);
      c.drawString(9 * MM, y, `Note : ${item.comment}`);
      y -= 3.5 * MM;
    }
  }

  separator();

  c.setFont('Helvetica-Bold', 10);
  c.drawString(5 * MM, y, 'TOTAL');
  c.drawRightString(width - 5 * MM, y, amount(order.amount_total));
  y -= 5 * MM;

  if (order.type !== 'onsite') {
    const status = order.payment_status ?? '';
    line(`Paiement : ${PAYMENT_LABELS[status] ?? status}`, { size: 8, gap: 3 });
  }

  separator();

  if ((order.type === 'delivery' || order.type === 'pickup') && order.customer) {
    const { customer } = order;
    line('Client', { bold: true, size: 8, gap: 3 });
    line(`${customer.first_name} ${customer.last_name}`, { size: 8, gap: 3 });
    if (customer.phone) line(`Tel : ${customer.phone}`, { size: 8, gap: 3 });
    if (order.type === 'delivery' && order.address) {
      line(order.address.street, { size: 8, gap: 3 });
      line(`${order.address.postal_code} ${order.address.city}`, { size: 8, gap: 3 });
    }
    y -= 2 * MM;
    if (order.comment) separator(true);
  }

  if (order.comment) {
    line('Commentaire :', { bold: true, size: 8, gap: 3 });
    line(order.comment, { size: 8, gap: 3 });
    y -= 2 * MM;
  }

  separator(true);
  line('Merci pour votre commande !', { size: 8, center: true, gap: 4 });

  const prefix = 'Propulsé par ';
  const brand = 'Yumco';
  const suffix = ' – Solutions de restauration';
  const prefixWidth = c.stringWidth(prefix, 'Helvetica', 7);
  const brandWidth = c.stringWidth(brand, 'Helvetica-Bold', 7);
  const suffixWidth = c.stringWidth(suffix, 'Helvetica', 7);
  const startX = (width - prefixWidth - brandWidth - suffixWidth) / 2;
  c.setFont('Helvetica', 7);
  c.drawString(startX, y, prefix);
  c.setFont('Helvetica-Bold', 7);
  c.drawString(startX + prefixWidth, y, brand);
  c.setFont('Helvetica', 7);
  c.drawString(startX + prefixWidth + brandWidth, y, suffix);

  return c.save();
};

/** Ticket posé sur la table : nom du restaurant, numéro de table en grand, emplacement et heure. */
export const generateTableTicket = (table: Table, restaurant: Restaurant): Promise<Buffer> => {
  const width = 80 * MM;
  const height = 110 * MM + (table.location ? 10 * MM : 0);
  const c = new Canvas(width, height);
  let y = height - 10 * MM;

  c.setFont('Helvetica', 10);
  c.drawCentredString(width / 2, y, restaurant.name);
  y -= 10 * MM;

  y -= 8 * MM;
  c.setFont('Helvetica-Bold', 48);
  c.drawCentredString(width / 2, y, String(table.table_number));
  y -= 18 * MM;

  if (table.location) {
    c.setFont('Helvetica', 9);
    c.drawCentredString(width / 2, y, table.location);
    y -= 8 * MM;
  }

  c.setFont('Helvetica', 8);
  c.drawCentredString(width / 2, y, `Occupée le ${localStamp(new Date(), restaurant)}`);
  y -= 12 * MM;

  c.setFont('Helvetica', 7);
  c.drawCentredString(width / 2, y, 'Propulsé par Yumco');

  return c.save();
};
