from io import BytesIO
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A6
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors


def generate_receipt(order, restaurant) -> BytesIO:
    buffer = BytesIO()
    width = 80 * mm  # largeur ticket thermique 80mm

    # Calcul de la hauteur nécessaire (contenu dynamique)
    # On estime et on ajuste — reportlab coupe si trop court, donc on prend large
    estimated_height = (
        40  # en-tête
        + 30  # date / type
        + len(order.items) * 14  # articles
        + 30  # total
        + 40  # client
        + 20  # pied
    ) * mm / 10
    height = max(estimated_height, 80 * mm)

    c = canvas.Canvas(buffer, pagesize=(width, height))
    y = height - 6 * mm

    def line(text, font="Helvetica", size=8, bold=False, center=False, gap=4):
        nonlocal y
        font_name = "Helvetica-Bold" if bold else font
        c.setFont(font_name, size)
        if center:
            c.drawCentredString(width / 2, y, text)
        else:
            c.drawString(5 * mm, y, text)
        y -= gap * mm

    def separator(dash=False):
        nonlocal y
        if dash:
            c.setDash(2, 2)
        c.setStrokeColor(colors.black)
        c.line(5 * mm, y, width - 5 * mm, y)
        c.setDash()
        y -= 5 * mm

    # --- En-tête ---
    line(restaurant.name, size=12, bold=True, center=True, gap=4)
    line(order.order_number, bold=True, size=10, center=True, gap=5)

    # --- Date puis mode de livraison (sans séparateur entre les deux) ---
    created = order.created_at.strftime("%d/%m/%Y à %H:%M")
    line(f"Date : {created}", size=8, center=True, gap=3)

    if order.requested_time:
        requested = order.requested_time.strftime("%d/%m/%Y à %H:%M")
        line(f"Pour : {requested}", size=8, center=True, gap=3)

    type_label = {"delivery": "Livraison", "pickup": "À emporter", "onsite": "Sur place"}.get(order.type, order.type)
    line(type_label, size=9, center=True, gap=4)

    if order.type == "onsite" and order.table_id:
        line(f"Table {order.table_id}", size=8, center=True, gap=3)

    separator()

    # --- Articles ---
    for item in order.items:
        if item.parent_order_item_id is not None:
            price_str = f"{float(item.unit_price):.2f} €" if float(item.unit_price) > 0 else ""
            c.setFont("Helvetica", 7)
            c.drawString(9 * mm, y, f"› {item.name}")
            if price_str:
                c.drawRightString(width - 5 * mm, y, price_str)
            y -= 3.5 * mm
        else:
            subtotal_str = f"{float(item.subtotal):.2f} €"
            name_display = f"{item.quantity}x {item.name}"
            c.setFont("Helvetica-Bold", 8)
            c.drawString(5 * mm, y, name_display)
            c.drawRightString(width - 5 * mm, y, subtotal_str)
            y -= 4 * mm
            if item.quantity > 1:
                c.setFont("Helvetica", 7)
                c.drawString(9 * mm, y, f"{float(item.unit_price):.2f} € / unité")
                y -= 3.5 * mm
        if item.comment:
            c.setFont("Helvetica-Oblique", 7)
            c.drawString(9 * mm, y, f"Note : {item.comment}")
            y -= 3.5 * mm

    separator()

    # --- Total ---
    c.setFont("Helvetica-Bold", 10)
    c.drawString(5 * mm, y, "TOTAL")
    c.drawRightString(width - 5 * mm, y, f"{float(order.amount_total):.2f} €")
    y -= 5 * mm

    if order.type != "onsite":
        payment_labels = {
            "unpaid": "Non payé",
            "awaiting_payment": "En attente de paiement",
            "paid": "Payé",
            "refunded": "Remboursé"
        }
        payment_label = payment_labels.get(order.payment_status, order.payment_status)
        line(f"Paiement : {payment_label}", size=8, gap=3)

    separator()

    # --- Infos client ---
    if order.type in ("delivery", "pickup") and order.customer:
        customer = order.customer
        line("Client", bold=True, size=8, gap=3)
        line(f"{customer.first_name} {customer.last_name}", size=8, gap=3)
        if customer.phone:
            line(f"Tel : {customer.phone}", size=8, gap=3)
        if order.type == "delivery" and order.address:
            addr = order.address
            line(addr.street, size=8, gap=3)
            line(f"{addr.postal_code} {addr.city}", size=8, gap=3)
        y -= 2 * mm
        if order.comment:
            separator(dash=True)

    # --- Commentaire client ---
    if order.comment:
        line("Commentaire :", bold=True, size=8, gap=3)
        line(order.comment, size=8, gap=3)
        y -= 2 * mm

    separator(dash=True)

    # --- Pied de page ---
    line("Merci pour votre commande !", size=8, center=True, gap=4)

    prefix = "Propulsé par "
    yumco = "Yumco"
    suffix = " – Solutions de restauration"
    prefix_w = c.stringWidth(prefix, "Helvetica", 7)
    yumco_w = c.stringWidth(yumco, "Helvetica-Bold", 7)
    suffix_w = c.stringWidth(suffix, "Helvetica", 7)
    start_x = (width - prefix_w - yumco_w - suffix_w) / 2
    c.setFont("Helvetica", 7)
    c.drawString(start_x, y, prefix)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(start_x + prefix_w, y, yumco)
    c.setFont("Helvetica", 7)
    c.drawString(start_x + prefix_w + yumco_w, y, suffix)
    y -= 5 * mm

    c.save()
    buffer.seek(0)
    return buffer


def generate_table_ticket(table, restaurant) -> BytesIO:
    buffer = BytesIO()
    width, height = A6

    c = canvas.Canvas(buffer, pagesize=A6)
    y = height - 15 * mm

    # Nom du restaurant
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, y, restaurant.name)
    y -= 10 * mm

    # Numéro de table en très grand
    y -= 15 * mm
    c.setFont("Helvetica-Bold", 72)
    c.drawCentredString(width / 2, y, str(table.table_number))
    y -= 28 * mm

    # Emplacement si défini
    if table.location:
        c.setFont("Helvetica", 9)
        c.drawCentredString(width / 2, y, table.location)
        y -= 8 * mm

    # Heure d'occupation
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y à %H:%M")
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, y, f"Occupée le {now}")
    y -= 15 * mm

    # Pied de page
    c.setFont("Helvetica", 7)
    c.drawCentredString(width / 2, y, "Propulsé par Yumco")

    c.save()
    buffer.seek(0)
    return buffer
