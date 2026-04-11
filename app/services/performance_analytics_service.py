from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.role import Role
from app.models.user import User
from app.services.order_analytics_service import _period_bounds, _to_float, _to_int


def get_performance_analytics(db: Session, restaurant_id: int):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        return None

    timezone_name = restaurant.timezone or "Europe/Paris"
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    bounds = _period_bounds(now_local)

    preparation_minutes_expr = func.extract("epoch", Order.completed_at - Order.created_at) / 60.0

    base_prepared_orders = db.query(Order).filter(
        Order.restaurant_id == restaurant_id,
        Order.status != "cancelled",
        Order.preparing_by.isnot(None),
        Order.completed_at.isnot(None),
    )

    current_month_average = _to_float(
        base_prepared_orders.filter(
            Order.completed_at >= bounds["month_start_utc"],
            Order.completed_at < bounds["next_month_start_utc"],
        ).with_entities(func.coalesce(func.avg(preparation_minutes_expr), 0)).scalar()
    )

    previous_month_average = _to_float(
        base_prepared_orders.filter(
            Order.completed_at >= bounds["previous_month_start_utc"],
            Order.completed_at < bounds["month_start_utc"],
        ).with_entities(func.coalesce(func.avg(preparation_minutes_expr), 0)).scalar()
    )

    preparer_rows = (
        db.query(
            User.id.label("user_id"),
            User.first_name.label("first_name"),
            func.count(Order.id).label("prepared_orders_count"),
            func.coalesce(func.avg(preparation_minutes_expr), 0).label("average_preparation_minutes"),
        )
        .join(Role, Role.user_id == User.id)
        .join(Order, Order.preparing_by == User.id)
        .filter(
            Role.restaurant_id == restaurant_id,
            Order.restaurant_id == restaurant_id,
            Order.status != "cancelled",
            Order.completed_at.isnot(None),
        )
        .group_by(User.id, User.first_name)
        .order_by(func.count(Order.id).desc(), User.first_name.asc())
        .all()
    )

    return {
        "preparation_time": {
            "average_minutes": round(current_month_average, 2),
            "difference_vs_previous_month_minutes": round(current_month_average - previous_month_average, 2),
        },
        "preparers": [
            {
                "user_id": _to_int(row.user_id),
                "first_name": row.first_name,
                "prepared_orders_count": _to_int(row.prepared_orders_count),
                "average_preparation_minutes": round(_to_float(row.average_preparation_minutes), 2),
            }
            for row in preparer_rows
        ],
    }
