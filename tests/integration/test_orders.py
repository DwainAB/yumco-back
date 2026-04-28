"""Tests d'intégration — commandes."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
