from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.restaurant import Restaurant
from app.services.order_analytics_service import _percentage_change, _period_bounds, _to_float, day_label, month_label


def get_revenue_analytics(db: Session, restaurant_id: int):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return None

    timezone_name = restaurant.timezone or "Europe/Paris"
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    bounds = _period_bounds(now_local)
    local_created_at = func.timezone(timezone_name, Order.created_at)
    local_month_bucket = func.date_trunc("month", local_created_at)
    local_day_bucket = func.date_trunc("day", local_created_at)

    base_orders = db.query(Order).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != "cancelled",
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

    current_month_revenue = _to_float(
        current_month_orders.with_entities(func.coalesce(func.sum(Order.amount_total), 0)).scalar()
    )
    previous_month_revenue = _to_float(
        previous_month_orders.with_entities(func.coalesce(func.sum(Order.amount_total), 0)).scalar()
    )
    current_month_average_basket = _to_float(
        current_month_orders.with_entities(func.coalesce(func.avg(Order.amount_total), 0)).scalar()
    )
    previous_month_average_basket = _to_float(
        previous_month_orders.with_entities(func.coalesce(func.avg(Order.amount_total), 0)).scalar()
    )
    current_year_revenue = _to_float(
        current_year_orders.with_entities(func.coalesce(func.sum(Order.amount_total), 0)).scalar()
    )
    previous_year_revenue = _to_float(
        previous_year_orders.with_entities(func.coalesce(func.sum(Order.amount_total), 0)).scalar()
    )

    yearly_channel_rows = (
        base_orders.with_entities(
            func.extract("year", local_created_at).label("year_value"),
            Order.type.label("order_type"),
            func.coalesce(func.sum(Order.amount_total), 0).label("amount"),
        )
        .filter(Order.type.in_(["delivery", "pickup"]))
        .group_by("year_value", Order.type)
        .order_by("year_value", Order.type)
        .all()
    )
    yearly_channels_map = {}
    for row in yearly_channel_rows:
        year_value = int(row.year_value)
        yearly_channels_map.setdefault(year_value, {"delivery_amount": 0.0, "pickup_amount": 0.0})
        if row.order_type == "delivery":
            yearly_channels_map[year_value]["delivery_amount"] = round(_to_float(row.amount), 2)
        if row.order_type == "pickup":
            yearly_channels_map[year_value]["pickup_amount"] = round(_to_float(row.amount), 2)

    yearly_breakdown_rows = (
        base_orders.with_entities(
            func.extract("year", local_created_at).label("year_value"),
            func.extract("month", local_created_at).label("month_value"),
            func.coalesce(func.sum(Order.amount_total), 0).label("amount"),
        )
        .group_by("year_value", "month_value")
        .order_by("year_value", "month_value")
        .all()
    )
    yearly_breakdown_map = {}
    for row in yearly_breakdown_rows:
        year_value = int(row.year_value)
        month_value = int(row.month_value)
        amount = round(_to_float(row.amount), 2)
        yearly_breakdown_map.setdefault(year_value, {"total_amount": 0.0, "months": []})
        yearly_breakdown_map[year_value]["total_amount"] += amount
        yearly_breakdown_map[year_value]["months"].append({"month": month_value, "amount": amount})

    best_revenue_month_row = (
        base_orders.with_entities(
            local_month_bucket.label("month_bucket"),
            func.coalesce(func.sum(Order.amount_total), 0).label("amount"),
        )
        .group_by("month_bucket")
        .order_by(func.sum(Order.amount_total).desc(), local_month_bucket.asc())
        .first()
    )

    best_revenue_day_row = (
        base_orders.with_entities(
            local_day_bucket.label("day_bucket"),
            func.coalesce(func.sum(Order.amount_total), 0).label("amount"),
        )
        .group_by("day_bucket")
        .order_by(func.sum(Order.amount_total).desc(), local_day_bucket.asc())
        .first()
    )

    yearly_channels = []
    for year_value in sorted(yearly_channels_map):
        delivery_amount = yearly_channels_map[year_value]["delivery_amount"]
        pickup_amount = yearly_channels_map[year_value]["pickup_amount"]
        year_total = delivery_amount + pickup_amount
        yearly_channels.append(
            {
                "year": year_value,
                "delivery": {
                    "amount": delivery_amount,
                    "percentage": round((delivery_amount / year_total) * 100, 2) if year_total else 0.0,
                },
                "pickup": {
                    "amount": pickup_amount,
                    "percentage": round((pickup_amount / year_total) * 100, 2) if year_total else 0.0,
                },
            }
        )

    yearly_breakdown = []
    for year_value in sorted(yearly_breakdown_map):
        total_amount = round(yearly_breakdown_map[year_value]["total_amount"], 2)
        months = []
        for month_entry in yearly_breakdown_map[year_value]["months"]:
            months.append(
                {
                    "month": month_label(month_entry["month"], year_value).split()[0],
                    "amount": month_entry["amount"],
                    "annual_percentage": round((month_entry["amount"] / total_amount) * 100, 2) if total_amount else 0.0,
                }
            )
        yearly_breakdown.append(
            {
                "year": year_value,
                "total_amount": total_amount,
                "months": months,
            }
        )

    return {
        "current_month_amount": round(current_month_revenue, 2),
        "current_month_change_percentage": _percentage_change(current_month_revenue, previous_month_revenue),
        "previous_month_amount": round(previous_month_revenue, 2),
        "yearly_channels": yearly_channels,
        "best_month": {
            "label": (
                month_label(best_revenue_month_row.month_bucket.month, best_revenue_month_row.month_bucket.year)
                if best_revenue_month_row and best_revenue_month_row.month_bucket
                else None
            ),
            "amount": round(_to_float(best_revenue_month_row.amount), 2) if best_revenue_month_row else 0.0,
        },
        "best_day": {
            "label": day_label(best_revenue_day_row.day_bucket) if best_revenue_day_row and best_revenue_day_row.day_bucket else None,
            "amount": round(_to_float(best_revenue_day_row.amount), 2) if best_revenue_day_row else 0.0,
        },
        "yearly_breakdown": yearly_breakdown,
        "annual_growth_percentage": _percentage_change(current_year_revenue, previous_year_revenue),
        "average_basket": {
            "amount": round(current_month_average_basket, 2),
            "change_percentage_vs_previous_month": _percentage_change(
                current_month_average_basket,
                previous_month_average_basket,
            ),
        },
    }
