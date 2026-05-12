from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.review_followup import ReviewFollowup
from tests.integration.conftest import auth_headers, make_category, make_product, make_restaurant, make_user


def _create_order(client: TestClient, restaurant_id: int, product_id: int, email: str) -> int:
    response = client.post(
        f"/restaurants/{restaurant_id}/orders",
        json={
            "type": "pickup",
            "items": [{"product_id": product_id, "quantity": 1}],
            "customer": {
                "first_name": "Jane",
                "last_name": "Doe",
                "phone": "+33600000099",
                "email": email,
            },
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_completed_order_schedules_review_followup(client: TestClient, db: Session, monkeypatch):
    async def fake_send_email(*args, **kwargs):
        return None

    monkeypatch.setattr("app.services.order_email_service.send_email", fake_send_email)

    user = make_user(db, email="owner_followup@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    restaurant.google_review_url = "https://g.page/r/test/review"
    db.commit()
    category = make_category(db, restaurant.id)
    product = make_product(db, restaurant.id, category.id)

    order_id = _create_order(client, restaurant.id, product.id, "review@test.com")

    response = client.post(
        f"/restaurants/{restaurant.id}/orders/{order_id}/status",
        json={"status": "completed"},
        headers=auth_headers(user.email),
    )
    assert response.status_code == 200

    followup = db.query(ReviewFollowup).filter(ReviewFollowup.order_id == order_id).first()
    assert followup is not None
    assert followup.status == "pending"
    assert followup.customer_email == "review@test.com"

    order_completed_at = response.json()["completed_at"]
    completed_at = datetime.fromisoformat(order_completed_at.replace("Z", "+00:00"))
    send_at_delta = followup.send_at - completed_at
    assert timedelta(hours=23, minutes=59) < send_at_delta < timedelta(hours=24, minutes=1)


def test_process_review_followups_route_sends_due_email(client: TestClient, db: Session, monkeypatch):
    async def fake_send_email(*args, **kwargs):
        return None

    async def fake_send_email_safe(*args, **kwargs):
        return True

    monkeypatch.setattr("app.services.order_email_service.send_email", fake_send_email)
    monkeypatch.setattr("app.services.order_email_service.send_email_safe", fake_send_email_safe)
    monkeypatch.setattr(settings, "REVIEW_FOLLOWUPS_CRON_SECRET", "super-secret")

    user = make_user(db, email="owner_process@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    restaurant.google_review_url = "https://g.page/r/test/review"
    db.commit()
    category = make_category(db, restaurant.id)
    product = make_product(db, restaurant.id, category.id)

    order_id = _create_order(client, restaurant.id, product.id, "process@test.com")
    complete_response = client.post(
        f"/restaurants/{restaurant.id}/orders/{order_id}/status",
        json={"status": "completed"},
        headers=auth_headers(user.email),
    )
    assert complete_response.status_code == 200

    followup = db.query(ReviewFollowup).filter(ReviewFollowup.order_id == order_id).first()
    assert followup is not None
    followup.send_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    response = client.post(
        "/internal/review-followups/process",
        headers={"X-Cron-Secret": "super-secret"},
    )
    assert response.status_code == 200
    assert response.json()["sent"] == 1

    db.refresh(followup)
    assert followup.status == "sent"
    assert followup.sent_at is not None
