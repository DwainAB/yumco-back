from io import BytesIO
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A6
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors


def generate_receipt(order, restaurant) -> BytesIO:
    buffer = BytesIO()
    width, height = A6  # 105mm x 148mm — ticket de caisse

    c = canvas.Canvas(buffer, pagesize=A6)
    y = height - 10 * mm  # curseur vertical, on descend au fur et à mesure

    def line(text, font="Helvetica", size=9, bold=False, center=False, gap=5):
        nonlocal y
        font_name = "Helvetica-Bold" if bold else font
        c.setFont(font_name, size)
        if center:
            c.drawCentredString(width / 2, y, text)
        else:
            c.drawString(10 * mm, y, text)
        y -= gap * mm

    def separator(dash=False):
        nonlocal y
        if dash:
            c.setDash(2, 2)
        c.setStrokeColor(colors.black)
        c.line(10 * mm, y, width - 10 * mm, y)
        c.setDash()
        y -= 4 * mm

    # --- En-tête ---
    line(restaurant.name, size=14, bold=True, center=True, gap=6)

    type_label = {"delivery": "Livraison", "pickup": "À emporter", "onsite": "Sur place"}.get(order.type, order.type)
    line(type_label, size=10, center=True, gap=4)

    # Numéro de table en gros si onsite
    if order.type == "onsite" and order.table_id:
        y -= 2 * mm
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(width / 2, y, f"Table {order.table_id}")
        y -= 8 * mm

    separator()

    # --- Numéro de commande + date ---
    line(f"Commande : {order.order_number}", bold=True, size=10, gap=4)

    created = order.created_at.strftime("%d/%m/%Y à %H:%M")
    line(f"Date : {created}", size=8, gap=4)

    if order.requested_time:
        requested = order.requested_time.strftime("%d/%m/%Y à %H:%M")
        line(f"À préparer pour : {requested}", size=8, gap=4)

    separator(dash=True)

    # --- Infos client (delivery / pickup uniquement) ---
    if order.type in ("delivery", "pickup") and order.customer:
        customer = order.customer
        line("Client", bold=True, size=9, gap=3)
        line(f"{customer.first_name} {customer.last_name}", size=9, gap=3)
        if customer.phone:
            line(f"Tel : {customer.phone}", size=8, gap=3)
        if order.type == "delivery" and order.address:
            addr = order.address
            line(f"{addr.street}", size=8, gap=3)
            line(f"{addr.postal_code} {addr.city}", size=8, gap=3)
        separator(dash=True)

    # --- Items ---
    line("Articles", bold=True, size=9, gap=4)

    for item in order.items:
        if item.parent_order_item_id is not None:
            # Option de menu — indentée
            price_str = f"{float(item.unit_price):.2f} €" if float(item.unit_price) > 0 else ""
            c.setFont("Helvetica", 7)
            c.drawString(15 * mm, y, f"  › {item.name}")
            if price_str:
                c.drawRightString(width - 10 * mm, y, price_str)
            y -= 4 * mm
        else:
            # Item principal
            subtotal_str = f"{float(item.subtotal):.2f} €"
            name_display = f"{item.quantity}x {item.name}"
            c.setFont("Helvetica-Bold", 9)
            c.drawString(10 * mm, y, name_display)
            c.drawRightString(width - 10 * mm, y, subtotal_str)
            y -= 4 * mm
            # Prix unitaire si quantité > 1
            if item.quantity > 1:
                c.setFont("Helvetica", 7)
                c.drawString(15 * mm, y, f"  {float(item.unit_price):.2f} € / unité")
                y -= 4 * mm
        if item.comment:
            c.setFont("Helvetica-Oblique", 7)
            c.drawString(15 * mm, y, f"  Note : {item.comment}")
            y -= 4 * mm

    separator()

    # --- Total ---
    c.setFont("Helvetica-Bold", 11)
    c.drawString(10 * mm, y, "TOTAL")
    c.drawRightString(width - 10 * mm, y, f"{float(order.amount_total):.2f} €")
    y -= 6 * mm

    payment_labels = {
        "unpaid": "Non payé",
        "awaiting_payment": "En attente de paiement",
        "pending": "En attente",
        "refunded": "Remboursé"
    }
    payment_label = payment_labels.get(order.payment_status, order.payment_status)
    line(f"Paiement : {payment_label}", size=8, gap=6)

    separator(dash=True)

    # --- Pied de page ---
    line("Merci pour votre commande !", size=8, center=True, gap=4)
    line("Propulsé par Yumco", size=7, center=True, gap=4)

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

    # Label "TABLE"
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y, "TABLE")
    y -= 18 * mm

    # Numéro de table en très grand
    c.setFont("Helvetica-Bold", 72)
    c.drawCentredString(width / 2, y, str(table.table_number))
    y -= 20 * mm

    # Capacité
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, y, f"{table.number_of_people} personnes")
    y -= 8 * mm

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
