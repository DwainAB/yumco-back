import csv
from datetime import date, datetime, time, timedelta
from io import BytesIO, StringIO
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session, joinedload

from app.models.order import Order
from app.models.restaurant import Restaurant


ORDER_TYPE_LABELS = {
    "delivery": "Livraison",
    "pickup": "A emporter",
    "onsite": "Sur place",
}

PAYMENT_STATUS_LABELS = {
    "unpaid": "Non paye",
    "awaiting_payment": "En attente",
    "paid": "Paye",
    "refunded": "Rembourse",
}


def _localize_datetime_range(
    timezone_name: str,
    start_date: date | None,
    end_date: date | None,
    month: int | None,
    year: int | None,
) -> tuple[datetime | None, datetime | None, str]:
    tz = ZoneInfo(timezone_name)

    if start_date and end_date and start_date > end_date:
        raise ValueError("date_from must be before or equal to date_to")

    if (start_date is None) != (end_date is None):
        raise ValueError("date_from and date_to must be provided together")

    if month is not None and year is None:
        raise ValueError("year is required when month is provided")

    if month is None and year is not None:
        raise ValueError("month is required when year is provided")

    if start_date and end_date:
        start_local = datetime.combine(start_date, time.min, tzinfo=tz)
        end_local = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
        period_label = f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
        return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC")), period_label

    if month is not None and year is not None:
        start_local = datetime(year, month, 1, tzinfo=tz)
        if month == 12:
            end_local = datetime(year + 1, 1, 1, tzinfo=tz)
        else:
            end_local = datetime(year, month + 1, 1, tzinfo=tz)
        period_label = start_local.strftime("%m/%Y")
        return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC")), period_label

    return None, None, "toutes_periodes"


def _format_amount(value) -> str:
    return f"{float(value or 0):.2f}"


def _format_local_datetime(value: datetime | None, timezone_name: str) -> str:
    if value is None:
        return ""
    tz = ZoneInfo(timezone_name)
    localized = value.astimezone(tz) if value.tzinfo else value.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    return localized.strftime("%d/%m/%Y %H:%M")


def _build_items_text(order: Order) -> str:
    main_items: list[str] = []
    children_by_parent: dict[int, list[str]] = {}

    for item in order.items:
        if item.parent_order_item_id is not None:
            children_by_parent.setdefault(item.parent_order_item_id, []).append(item.name)

    for item in order.items:
        if item.parent_order_item_id is not None:
            continue
        label = f"{item.quantity}x {item.name}"
        options = children_by_parent.get(item.id)
        if options:
            label = f"{label} ({', '.join(options)})"
        main_items.append(label)

    return " | ".join(main_items)


def get_export_orders(
    db: Session,
    restaurant_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    month: int | None = None,
    year: int | None = None,
):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return None

    timezone_name = restaurant.timezone or "Europe/Paris"
    start_utc, end_utc, period_label = _localize_datetime_range(
        timezone_name=timezone_name,
        start_date=start_date,
        end_date=end_date,
        month=month,
        year=year,
    )

    query = (
        db.query(Order)
        .options(
            joinedload(Order.items),
            joinedload(Order.customer),
            joinedload(Order.address),
        )
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status == "completed",
            Order.is_draft.is_(False),
        )
    )

    if start_utc is not None:
        query = query.filter(Order.created_at >= start_utc)
    if end_utc is not None:
        query = query.filter(Order.created_at < end_utc)

    orders = query.order_by(Order.created_at.asc(), Order.id.asc()).all()
    return restaurant, orders, timezone_name, period_label


def build_order_export_summary(orders: list[Order]) -> dict:
    summary = {
        "orders_count": len(orders),
        "amount_total": 0.0,
        "items_subtotal": 0.0,
        "delivery_fee_total": 0.0,
        "discount_total": 0.0,
        "average_basket": 0.0,
        "delivery_count": 0,
        "pickup_count": 0,
        "onsite_count": 0,
    }

    for order in orders:
        summary["amount_total"] += float(order.amount_total or 0)
        summary["items_subtotal"] += float(order.items_subtotal or 0)
        summary["delivery_fee_total"] += float(order.delivery_fee or 0)
        summary["discount_total"] += float(order.discount_amount or 0)
        if order.type == "delivery":
            summary["delivery_count"] += 1
        elif order.type == "pickup":
            summary["pickup_count"] += 1
        elif order.type == "onsite":
            summary["onsite_count"] += 1

    if summary["orders_count"] > 0:
        summary["average_basket"] = summary["amount_total"] / summary["orders_count"]

    for key in ("amount_total", "items_subtotal", "delivery_fee_total", "discount_total", "average_basket"):
        summary[key] = round(summary[key], 2)

    return summary


def generate_orders_csv(
    restaurant: Restaurant,
    orders: list[Order],
    timezone_name: str,
    period_label: str,
) -> BytesIO:
    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Restaurant", restaurant.name])
    writer.writerow(["Periode", period_label])
    writer.writerow([])
    writer.writerow(
        [
            "Numero",
            "Date commande",
            "Date completion",
            "Type",
            "Statut",
            "Paiement",
            "Sous-total articles",
            "Remise",
            "Frais livraison",
            "Total",
            "Client",
            "Telephone",
            "Email",
            "Adresse / Table",
            "Articles",
            "Commentaire",
        ]
    )

    for order in orders:
        customer_name = ""
        customer_phone = ""
        customer_email = ""
        if order.customer:
            customer_name = f"{order.customer.first_name} {order.customer.last_name}".strip()
            customer_phone = order.customer.phone or ""
            customer_email = order.customer.email or ""

        address_or_table = ""
        if order.address:
            address_or_table = f"{order.address.street}, {order.address.postal_code} {order.address.city}"
        elif order.table_id is not None:
            address_or_table = f"Table {order.table_id}"

        writer.writerow(
            [
                order.order_number,
                _format_local_datetime(order.created_at, timezone_name),
                _format_local_datetime(order.completed_at, timezone_name),
                ORDER_TYPE_LABELS.get(order.type, order.type),
                order.status,
                PAYMENT_STATUS_LABELS.get(order.payment_status, order.payment_status),
                _format_amount(order.items_subtotal),
                _format_amount(order.discount_amount),
                _format_amount(order.delivery_fee),
                _format_amount(order.amount_total),
                customer_name,
                customer_phone,
                customer_email,
                address_or_table,
                _build_items_text(order),
                order.comment or "",
            ]
        )

    return BytesIO(("\ufeff" + output.getvalue()).encode("utf-8"))


def generate_orders_summary_pdf(
    restaurant: Restaurant,
    orders: list[Order],
    timezone_name: str,
    period_label: str,
) -> BytesIO:
    summary = build_order_export_summary(orders)
    buffer = BytesIO()
    page_width, page_height = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    left_margin = 18 * mm
    right_margin = page_width - (18 * mm)
    y = page_height - (20 * mm)

    def draw_text(text: str, size: int = 10, bold: bool = False, color=colors.black, gap: float = 6):
        nonlocal y
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(left_margin, y, text)
        y -= gap * mm

    def ensure_space(required_mm: float):
        nonlocal y
        if y <= required_mm * mm:
            c.showPage()
            y = page_height - (20 * mm)

    draw_text(restaurant.name, size=18, bold=True, gap=4)
    draw_text("Recapitulatif des commandes", size=13, bold=True, gap=3)
    draw_text(f"Periode : {period_label}", size=10, color=colors.HexColor("#555555"), gap=8)

    metrics = [
        f"Commandes completes : {summary['orders_count']}",
        f"Chiffre d'affaires : {summary['amount_total']:.2f} EUR",
        f"Panier moyen : {summary['average_basket']:.2f} EUR",
        f"Remises : {summary['discount_total']:.2f} EUR",
        f"Frais de livraison : {summary['delivery_fee_total']:.2f} EUR",
        (
            f"Canaux : livraison {summary['delivery_count']} | "
            f"a emporter {summary['pickup_count']} | sur place {summary['onsite_count']}"
        ),
    ]
    for metric in metrics:
        draw_text(metric, size=10, gap=4)

    y -= 2 * mm
    c.setStrokeColor(colors.HexColor("#D8D8D8"))
    c.line(left_margin, y, right_margin, y)
    y -= 8 * mm

    headers = ["Numero", "Date", "Type", "Client", "Total"]
    positions = [left_margin, 52 * mm, 92 * mm, 122 * mm, 178 * mm]
    c.setFont("Helvetica-Bold", 9)
    for header, x in zip(headers, positions):
        c.drawString(x, y, header)
    y -= 5 * mm
    c.setStrokeColor(colors.HexColor("#E6E6E6"))
    c.line(left_margin, y, right_margin, y)
    y -= 5 * mm

    c.setFont("Helvetica", 8)
    for order in orders:
        ensure_space(20)
        customer_name = ""
        if order.customer:
            customer_name = f"{order.customer.first_name} {order.customer.last_name}".strip()

        row_values = [
            order.order_number,
            _format_local_datetime(order.created_at, timezone_name),
            ORDER_TYPE_LABELS.get(order.type, order.type),
            customer_name[:26],
            f"{float(order.amount_total or 0):.2f} EUR",
        ]

        for value, x in zip(row_values, positions):
            c.drawString(x, y, value)
        y -= 4.5 * mm

        items_text = _build_items_text(order)
        if items_text:
            c.setFillColor(colors.HexColor("#555555"))
            c.drawString(left_margin + (4 * mm), y, items_text[:110])
            c.setFillColor(colors.black)
            y -= 4.5 * mm

        c.setStrokeColor(colors.HexColor("#F0F0F0"))
        c.line(left_margin, y, right_margin, y)
        y -= 4 * mm

    c.save()
    buffer.seek(0)
    return buffer
