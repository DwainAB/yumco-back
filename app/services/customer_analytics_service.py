from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.services.order_analytics_service import MONTH_LABELS, _percentage_change, _period_bounds, _to_float


def _normalize_identity(email: str | None, phone: str | None, customer_id: int) -> str:
    normalized_email = email.strip().lower() if email else None
    normalized_phone = "".join(char for char in (phone or "") if char.isdigit()) or None
    return normalized_email or normalized_phone or f"customer:{customer_id}"


def get_customer_analytics(db: Session, restaurant_id: int):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return None

    timezone_name = restaurant.timezone or "Europe/Paris"
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    bounds = _period_bounds(now_local)

    rows = (
        db.query(
            Customer.id.label("customer_id"),
            Customer.first_name.label("first_name"),
            Customer.last_name.label("last_name"),
            Customer.email.label("email"),
            Customer.phone.label("phone"),
            Order.id.label("order_id"),
            Order.amount_total.label("amount_total"),
            Order.created_at.label("order_created_at"),
        )
        .join(Order, Order.customer_id == Customer.id)
        .filter(
            Customer.restaurant_id == restaurant_id,
            Order.restaurant_id == restaurant_id,
            Order.status != "cancelled",
        )
        .order_by(Order.created_at.asc())
        .all()
    )

    customers = {}
    new_customers_by_month = defaultdict(int)

    for row in rows:
        identity = _normalize_identity(row.email, row.phone, row.customer_id)
        created_at_local = row.order_created_at.astimezone(tz)

        if identity not in customers:
            customers[identity] = {
                "identity": identity,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "orders_count": 0,
                "total_spent": 0.0,
                "last_order_at": created_at_local,
                "first_order_at": created_at_local,
            }
            new_customers_by_month[(created_at_local.year, created_at_local.month)] += 1

        customer = customers[identity]
        customer["orders_count"] += 1
        customer["total_spent"] += _to_float(row.amount_total)

        if created_at_local > customer["last_order_at"]:
            customer["last_order_at"] = created_at_local
            customer["first_name"] = row.first_name
            customer["last_name"] = row.last_name

    loyal_customers_count = sum(1 for customer in customers.values() if customer["orders_count"] >= 2)
    total_customers_count = len(customers)
    previous_month_total_customers = sum(
        1 for customer in customers.values() if customer["first_order_at"].astimezone(tz) < bounds["month_start_utc"].astimezone(tz)
    )

    top_customers = sorted(
        customers.values(),
        key=lambda customer: (-customer["orders_count"], -customer["total_spent"], -customer["last_order_at"].timestamp()),
    )[:3]

    years_map = defaultdict(list)
    sorted_new_customers = sorted(new_customers_by_month.items())
    previous_count = None
    for (year_value, month_value), count in sorted_new_customers:
        years_map[year_value].append(
            {
                "month": MONTH_LABELS[month_value],
                "count": count,
                "change_percentage_vs_previous_month": _percentage_change(count, previous_count) if previous_count is not None else None,
            }
        )
        previous_count = count

    return {
        "total_customers": {
            "total": total_customers_count,
            "change_percentage_vs_previous_month": _percentage_change(total_customers_count, previous_month_total_customers),
        },
        "loyal_customers": {
            "total": loyal_customers_count,
            "percentage_of_total_customers": round((loyal_customers_count / total_customers_count) * 100, 2) if total_customers_count else 0.0,
        },
        "top_customers": [
            {
                "identity": customer["identity"],
                "first_name": customer["first_name"],
                "last_name": customer["last_name"],
                "orders_count": customer["orders_count"],
                "total_spent": round(customer["total_spent"], 2),
                "last_order_at": customer["last_order_at"],
            }
            for customer in top_customers
        ],
        "new_customers_breakdown": [
            {
                "year": year_value,
                "months": months,
            }
            for year_value, months in sorted(years_map.items())
        ],
    }
