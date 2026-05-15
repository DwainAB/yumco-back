"""Tests d'intégration — commandes."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.restaurant_promo_code import RestaurantPromoCode
from app.models.order import Order

from tests.integration.conftest import (
    make_user, make_restaurant, make_category, make_product, auth_headers
)


@pytest.fixture()
def setup(db: Session):
    user = make_user(db, email="owner_orders@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    category = make_category(db, restaurant.id)
    product = make_product(db, restaurant.id, category.id, price=12.50)
    return {"user": user, "restaurant": restaurant, "product": product}


def test_create_pickup_order(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    p = setup["product"]

    res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "pickup",
        "items": [{"product_id": p.id, "quantity": 2}],
        "customer": {
            "first_name": "Jane",
            "last_name": "Doe",
            "phone": "+33600000002",
            "email": "jane@test.com",
        },
    })
    assert res.status_code == 201
    data = res.json()
    assert data["type"] == "pickup"
    assert data["status"] == "pending"
    assert float(data["items_subtotal"]) == pytest.approx(25.0)


def test_create_order_wrong_product(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "pickup",
        "items": [{"product_id": 99999, "quantity": 1}],
        "customer": {"first_name": "Jane", "last_name": "Doe", "phone": "+33600000003"},
    })
    assert res.status_code == 400


def test_update_order_status(client: TestClient, db: Session, setup):
    u = setup["user"]
    r = setup["restaurant"]
    p = setup["product"]

    res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "pickup",
        "items": [{"product_id": p.id, "quantity": 1}],
        "customer": {"first_name": "Jane", "last_name": "Doe", "phone": "+33600000004"},
    })
    assert res.status_code == 201
    order_id = res.json()["id"]

    res = client.post(
        f"/restaurants/{r.id}/orders/{order_id}/status",
        json={"status": "preparing"},
        headers=auth_headers(u.email),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "preparing"


def test_list_orders(client: TestClient, db: Session, setup):
    u = setup["user"]
    r = setup["restaurant"]
    p = setup["product"]

    for i in range(2):
        client.post(f"/restaurants/{r.id}/orders", json={
            "type": "pickup",
            "items": [{"product_id": p.id, "quantity": 1}],
            "customer": {"first_name": "Jane", "last_name": "Doe", "phone": f"+3360000100{i}"},
        })

    res = client.get(f"/restaurants/{r.id}/orders", headers=auth_headers(u.email))
    assert res.status_code == 200
    assert len(res.json()) >= 2


def test_delete_draft_onsite_order(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    p = setup["product"]
    u = setup["user"]

    res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": p.id, "quantity": 1}],
    })
    assert res.status_code == 201
    order_id = res.json()["id"]

    res = client.delete(
        f"/restaurants/{r.id}/orders/{order_id}",
        headers=auth_headers(u.email),
    )
    assert res.status_code == 204


def test_order_total_calculation(client: TestClient, db: Session, setup):
    """Vérifie que le calcul du total est correct."""
    r = setup["restaurant"]
    p = setup["product"]  # prix: 12.50

    res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "pickup",
        "items": [{"product_id": p.id, "quantity": 3}],
        "customer": {"first_name": "Jane", "last_name": "Doe", "phone": "+33600000005"},
    })
    assert res.status_code == 201
    data = res.json()
    assert float(data["items_subtotal"]) == pytest.approx(37.5)


def test_validate_promo_code(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    p = setup["product"]
    db.add(
        RestaurantPromoCode(
            restaurant_id=r.id,
            code="YUM10",
            discount_type="percent",
            discount_value=10,
            is_active=True,
        )
    )
    db.commit()

    res = client.post(f"/restaurants/{r.id}/promo-codes/validate", json={
        "promo_code": "yum10",
        "type": "pickup",
        "items": [{"product_id": p.id, "quantity": 2}],
    })
    assert res.status_code == 200
    data = res.json()
    assert data["promo_code"] == "YUM10"
    assert float(data["items_subtotal"]) == pytest.approx(25.0)
    assert float(data["discount_amount"]) == pytest.approx(2.5)
    assert float(data["amount_total"]) == pytest.approx(22.5)


def test_create_pickup_order_with_promo_code(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    p = setup["product"]
    db.add(
        RestaurantPromoCode(
            restaurant_id=r.id,
            code="EURO5",
            discount_type="fixed",
            discount_value=5,
            is_active=True,
        )
    )
    db.commit()

    res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "pickup",
        "promo_code": "EURO5",
        "items": [{"product_id": p.id, "quantity": 2}],
        "customer": {
            "first_name": "Jane",
            "last_name": "Doe",
            "phone": "+33600000007",
            "email": "jane-promo@test.com",
        },
    })
    assert res.status_code == 201
    data = res.json()
    assert data["promo_code"] == "EURO5"
    assert float(data["amount_before_discount"]) == pytest.approx(25.0)
    assert float(data["discount_amount"]) == pytest.approx(5.0)
    assert float(data["amount_total"]) == pytest.approx(20.0)


def test_export_orders_csv_for_selected_month(client: TestClient, db: Session, setup):
    u = setup["user"]
    r = setup["restaurant"]
    p = setup["product"]

    first = client.post(
        f"/restaurants/{r.id}/orders",
        json={
            "type": "pickup",
            "items": [{"product_id": p.id, "quantity": 2}],
            "customer": {"first_name": "Jane", "last_name": "Doe", "phone": "+33600000008", "email": "jane-csv@test.com"},
        },
    )
    second = client.post(
        f"/restaurants/{r.id}/orders",
        json={
            "type": "delivery",
            "items": [{"product_id": p.id, "quantity": 1}],
            "customer": {"first_name": "John", "last_name": "Smith", "phone": "+33600000009", "email": "john-csv@test.com"},
            "address": {"street": "2 Rue du Test", "city": "Paris", "postal_code": "75002", "country": "FR"},
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    may_order = db.query(Order).filter(Order.id == first.json()["id"]).first()
    june_order = db.query(Order).filter(Order.id == second.json()["id"]).first()
    may_order.status = "completed"
    may_order.payment_status = "paid"
    may_order.completed_at = datetime(2026, 5, 10, 12, 30, tzinfo=timezone.utc)
    may_order.created_at = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
    june_order.status = "completed"
    june_order.payment_status = "paid"
    june_order.completed_at = datetime(2026, 6, 3, 12, 30, tzinfo=timezone.utc)
    june_order.created_at = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
    db.commit()

    res = client.get(
        f"/restaurants/{r.id}/orders/export?format=csv&month=5&year=2026",
        headers=auth_headers(u.email),
    )

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    body = res.content.decode("utf-8")
    assert "Restaurant;Test Restaurant" in body
    assert may_order.order_number in body
    assert june_order.order_number not in body
    assert "2x Burger" in body


def test_export_orders_pdf_returns_pdf_file(client: TestClient, db: Session, setup):
    u = setup["user"]
    r = setup["restaurant"]
    p = setup["product"]

    created = client.post(
        f"/restaurants/{r.id}/orders",
        json={
            "type": "onsite",
            "items": [{"product_id": p.id, "quantity": 1}],
        },
    )
    assert created.status_code == 201

    order = db.query(Order).filter(Order.id == created.json()["id"]).first()
    order.status = "completed"
    order.payment_status = "paid"
    order.completed_at = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    db.commit()

    res = client.get(
        f"/restaurants/{r.id}/orders/export?format=pdf",
        headers=auth_headers(u.email),
    )

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"].endswith(".pdf\"")
    assert res.content.startswith(b"%PDF")


def test_export_orders_requires_complete_date_range(client: TestClient, db: Session, setup):
    u = setup["user"]
    r = setup["restaurant"]

    res = client.get(
        f"/restaurants/{r.id}/orders/export?format=csv&date_from=2026-05-01",
        headers=auth_headers(u.email),
    )

    assert res.status_code == 400
    assert res.json()["detail"] == "date_from and date_to must be provided together"


def test_list_orders_by_custom_date_range(client: TestClient, db: Session, setup):
    u = setup["user"]
    r = setup["restaurant"]
    p = setup["product"]

    first = client.post(
        f"/restaurants/{r.id}/orders",
        json={
            "type": "pickup",
            "items": [{"product_id": p.id, "quantity": 1}],
            "customer": {"first_name": "Jane", "last_name": "Doe", "phone": "+33600000010"},
        },
    )
    second = client.post(
        f"/restaurants/{r.id}/orders",
        json={
            "type": "pickup",
            "items": [{"product_id": p.id, "quantity": 1}],
            "customer": {"first_name": "John", "last_name": "Smith", "phone": "+33600000011"},
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    may_order = db.query(Order).filter(Order.id == first.json()["id"]).first()
    june_order = db.query(Order).filter(Order.id == second.json()["id"]).first()
    may_order.status = "completed"
    may_order.created_at = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    june_order.status = "completed"
    june_order.created_at = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    db.commit()

    res = client.get(
        f"/restaurants/{r.id}/orders?status=completed&date_from=2026-05-01&date_to=2026-05-31",
        headers=auth_headers(u.email),
    )

    assert res.status_code == 200
    payload = res.json()
    assert len(payload) == 1
    assert payload[0]["id"] == may_order.id
