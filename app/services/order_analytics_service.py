from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.models.address import Address
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.restaurant import Restaurant


WEEKDAY_LABELS = {
    0: "Lundi",
    1: "Mardi",
    2: "Mercredi",
    3: "Jeudi",
    4: "Vendredi",
    5: "Samedi",
    6: "Dimanche",
}

MONTH_LABELS = {
    1: "Janvier",
    2: "Fevrier",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Aout",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Decembre",
}


def _to_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _to_int(value) -> int:
    if value is None:
        return 0
    return int(value)


def _percentage_change(current: float, previous: float) -> float | None:
    if previous == 0:
        if current == 0:
            return 0.0
        return 100.0
    return round(((current - previous) / previous) * 100, 2)


def _period_bounds(now_local: datetime):
    month_start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start_local.month == 1:
        previous_month_start_local = month_start_local.replace(year=month_start_local.year - 1, month=12)
    else:
        previous_month_start_local = month_start_local.replace(month=month_start_local.month - 1)
    if month_start_local.month == 12:
        next_month_start_local = month_start_local.replace(year=month_start_local.year + 1, month=1)
    else:
        next_month_start_local = month_start_local.replace(month=month_start_local.month + 1)
    current_year_start_local = now_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_year_start_local = current_year_start_local.replace(year=current_year_start_local.year - 1)
    next_year_start_local = current_year_start_local.replace(year=current_year_start_local.year + 1)
    return {
        "month_start_utc": month_start_local.astimezone(ZoneInfo("UTC")),
        "previous_month_start_utc": previous_month_start_local.astimezone(ZoneInfo("UTC")),
        "next_month_start_utc": next_month_start_local.astimezone(ZoneInfo("UTC")),
        "current_year_start_utc": current_year_start_local.astimezone(ZoneInfo("UTC")),
        "previous_year_start_utc": previous_year_start_local.astimezone(ZoneInfo("UTC")),
        "next_year_start_utc": next_year_start_local.astimezone(ZoneInfo("UTC")),
    }


def month_label(month_value: int, year_value: int) -> str:
    return f"{MONTH_LABELS[month_value]} {year_value}"


def day_label(value: datetime) -> str:
    return f"{value.day} {MONTH_LABELS[value.month]} {value.year}"


def get_order_analytics(db: Session, restaurant_id: int):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return None

    timezone_name = restaurant.timezone or "Europe/Paris"
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    bounds = _period_bounds(now_local)
    local_created_at = func.timezone(timezone_name, Order.created_at)
    local_month_bucket = func.date_trunc("month", local_created_at)
    item_type_case = case(
        (OrderItem.product_id.isnot(None), "product"),
        else_="menu_choice",
    )

    base_orders = db.query(Order).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != "cancelled",
    )

    top_items_rows = (
        db.query(
            OrderItem.name.label("item_name"),
            func.sum(OrderItem.quantity).label("quantity_sold"),
            func.sum(OrderItem.subtotal).label("revenue"),
            item_type_case.label("item_type"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != "cancelled",
            or_(OrderItem.product_id.isnot(None), OrderItem.menu_option_id.isnot(None)),
        )
        .group_by(OrderItem.name, OrderItem.product_id, OrderItem.menu_option_id, item_type_case)
        .order_by(func.sum(OrderItem.quantity).desc(), func.sum(OrderItem.subtotal).desc())
        .limit(10)
        .all()
    )

    current_month_orders = base_orders.filter(
        Order.created_at >= bounds["month_start_utc"],
        Order.created_at < bounds["next_month_start_utc"],
    )
    previous_month_orders = base_orders.filter(
        Order.created_at >= bounds["previous_month_start_utc"],
        Order.created_at < bounds["month_start_utc"],
    )
    current_year_orders = base_orders.filter(
        Order.created_at >= bounds["current_year_start_utc"],
        Order.created_at < bounds["next_year_start_utc"],
    )
    previous_year_orders = base_orders.filter(
        Order.created_at >= bounds["previous_year_start_utc"],
        Order.created_at < bounds["current_year_start_utc"],
    )

    current_month_orders_count = current_month_orders.count()
    previous_month_orders_count = previous_month_orders.count()
    current_month_revenue = _to_float(
        current_month_orders.with_entities(func.coalesce(func.sum(Order.amount_total), 0)).scalar()
    )
    previous_month_revenue = _to_float(
        previous_month_orders.with_entities(func.coalesce(func.sum(Order.amount_total), 0)).scalar()
    )
    current_year_orders_count = current_year_orders.count()
    current_year_average_basket = _to_float(
        current_year_orders.with_entities(func.coalesce(func.avg(Order.amount_total), 0)).scalar()
    )
    previous_year_average_basket = _to_float(
        previous_year_orders.with_entities(func.coalesce(func.avg(Order.amount_total), 0)).scalar()
    )

    online_type_rows = (
        base_orders.with_entities(
            Order.type,
            func.count(Order.id).label("orders_count"),
        )
        .filter(Order.type.in_(["delivery", "pickup"]))
        .group_by(Order.type)
        .all()
    )
    delivery_count = 0
    pickup_count = 0
    for row in online_type_rows:
        if row.type == "delivery":
            delivery_count = _to_int(row.orders_count)
        if row.type == "pickup":
            pickup_count = _to_int(row.orders_count)
    online_total = delivery_count + pickup_count

    top_delivery_cities_rows = (
        db.query(
            Address.city,
            func.count(Order.id).label("orders_count"),
        )
        .join(Order, Order.address_id == Address.id)
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != "cancelled",
            Order.type == "delivery",
        )
        .group_by(Address.city)
        .order_by(func.count(Order.id).desc(), Address.city.asc())
        .limit(10)
        .all()
    )

    best_month_orders_row = (
        base_orders.with_entities(
            local_month_bucket.label("month_bucket"),
            func.count(Order.id).label("orders_count"),
        )
        .group_by("month_bucket")
        .order_by(func.count(Order.id).desc(), local_month_bucket.asc())
        .first()
    )

    largest_order_row = base_orders.order_by(Order.amount_total.desc(), Order.created_at.desc()).first()

    weekday_rows = (
        base_orders.with_entities(
            func.extract("dow", local_created_at).label("weekday"),
            func.count(Order.id).label("orders_count"),
        )
        .group_by("weekday")
        .order_by(func.count(Order.id).desc(), func.extract("dow", local_created_at).asc())
        .all()
    )

    hour_rows = (
        base_orders.with_entities(
            func.extract("hour", local_created_at).label("hour_of_day"),
            func.count(Order.id).label("orders_count"),
        )
        .group_by("hour_of_day")
        .all()
    )
    hourly_counts = {int(row.hour_of_day): _to_int(row.orders_count) for row in hour_rows}
    busiest_slot = {"slot": None, "orders_count": 0}
    for start_hour in range(23):
        slot_count = hourly_counts.get(start_hour, 0) + hourly_counts.get(start_hour + 1, 0)
        if slot_count > busiest_slot["orders_count"]:
            busiest_slot = {
                "slot": f"{start_hour:02d}:00-{(start_hour + 2) % 24:02d}:00",
                "orders_count": slot_count,
            }

    customer_rows = (
        db.query(
            func.lower(func.trim(Customer.email)).label("email_key"),
            func.regexp_replace(func.coalesce(Customer.phone, ""), r"\\D", "", "g").label("phone_key"),
            func.count(Order.id).label("orders_count"),
        )
        .join(Order, Order.customer_id == Customer.id)
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != "cancelled",
        )
        .group_by(
            func.lower(func.trim(Customer.email)),
            func.regexp_replace(func.coalesce(Customer.phone, ""), r"\\D", "", "g"),
            Customer.id,
        )
        .all()
    )
    customer_buckets = {}
    for row in customer_rows:
        identity = row.email_key or row.phone_key or None
        if not identity:
            continue
        customer_buckets.setdefault(identity, 0)
        customer_buckets[identity] += _to_int(row.orders_count)
    identifiable_customers = len(customer_buckets)
    repeat_customers = sum(1 for orders_count in customer_buckets.values() if orders_count >= 2)

    return {
        "top_items": [
            {
                "item_name": row.item_name,
                "item_type": row.item_type,
                "quantity_sold": _to_int(row.quantity_sold),
                "revenue": round(_to_float(row.revenue), 2),
            }
            for row in top_items_rows
        ],
        "monthly_orders_count": current_month_orders_count,
        "monthly_orders_change": current_month_orders_count - previous_month_orders_count,
        "monthly_orders_change_percentage": _percentage_change(current_month_orders_count, previous_month_orders_count),
        "monthly_revenue_change_percentage": _percentage_change(current_month_revenue, previous_month_revenue),
        "delivery_percentage": round((delivery_count / online_total) * 100, 2) if online_total else 0.0,
        "pickup_percentage": round((pickup_count / online_total) * 100, 2) if online_total else 0.0,
        "top_delivery_cities": [
            {
                "city": row.city,
                "orders_count": _to_int(row.orders_count),
            }
            for row in top_delivery_cities_rows
        ],
        "best_month": {
            "label": (
                month_label(best_month_orders_row.month_bucket.month, best_month_orders_row.month_bucket.year)
                if best_month_orders_row and best_month_orders_row.month_bucket
                else None
            ),
            "orders_count": _to_int(best_month_orders_row.orders_count) if best_month_orders_row else 0,
        },
        "largest_order": (
            {
                "amount": round(_to_float(largest_order_row.amount_total), 2),
                "created_at": largest_order_row.created_at,
            }
            if largest_order_row
            else None
        ),
        "current_year_orders_count": current_year_orders_count,
        "average_basket": {
            "amount": round(current_year_average_basket, 2),
            "change_percentage_vs_previous_year": _percentage_change(
                current_year_average_basket,
                previous_year_average_basket,
            ),
        },
        "busiest_days": [
            {
                "day": WEEKDAY_LABELS[(int(row.weekday) - 1) % 7],
                "orders_count": _to_int(row.orders_count),
            }
            for row in weekday_rows
        ],
        "busiest_time_slot": busiest_slot,
        "repeat_purchase": {
            "rate_percentage": round((repeat_customers / identifiable_customers) * 100, 2) if identifiable_customers else None,
            "repeat_customers": repeat_customers,
            "identifiable_customers": identifiable_customers,
        },
    }
