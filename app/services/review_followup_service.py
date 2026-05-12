from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.review_followup import ReviewFollowup
from app.services.order_email_service import send_review_followup_email


REVIEW_FOLLOWUP_DELAY = timedelta(hours=24)


def schedule_review_followup(db: Session, order: Order, restaurant: Restaurant) -> ReviewFollowup | None:
    if not order.completed_at:
        return None
    if not order.customer or not order.customer.email:
        return None
    if not restaurant.google_review_url:
        return None

    existing = db.query(ReviewFollowup).filter(ReviewFollowup.order_id == order.id).first()
    if existing:
        return existing

    followup = ReviewFollowup(
        order_id=order.id,
        restaurant_id=restaurant.id,
        customer_email=order.customer.email,
        customer_first_name=order.customer.first_name,
        status="pending",
        send_at=order.completed_at + REVIEW_FOLLOWUP_DELAY,
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)
    return followup


def process_due_review_followups(db: Session, limit: int = 100) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    due_followups = (
        db.query(ReviewFollowup)
        .filter(ReviewFollowup.status == "pending", ReviewFollowup.send_at <= now)
        .order_by(ReviewFollowup.send_at.asc())
        .limit(limit)
        .all()
    )

    sent_count = 0
    failed_count = 0
    cancelled_count = 0

    for followup in due_followups:
        order = db.query(Order).filter(Order.id == followup.order_id).first()
        restaurant = db.query(Restaurant).filter(Restaurant.id == followup.restaurant_id).first()

        if not order or not restaurant or not restaurant.google_review_url:
            followup.status = "cancelled"
            followup.last_error = "Missing order, restaurant, or google review url"
            cancelled_count += 1
            continue

        sent = asyncio.run(
            send_review_followup_email(
                order=order,
                restaurant=restaurant,
                to_email=followup.customer_email,
                customer_first_name=followup.customer_first_name,
            )
        )
        if sent:
            followup.status = "sent"
            followup.sent_at = now
            followup.last_error = None
            sent_count += 1
        else:
            followup.status = "failed"
            followup.last_error = "Email send failed"
            failed_count += 1

    if due_followups:
        db.commit()

    return {
        "processed": len(due_followups),
        "sent": sent_count,
        "failed": failed_count,
        "cancelled": cancelled_count,
    }
