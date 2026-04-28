"""Tests d'intégration — commandes onsite (draft → submit → status)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.integration.conftest import make_user, make_restaurant, make_category, make_product, auth_headers


@pytest.fixture()
def setup(db: Session):
    user = make_user(db, email="owner_onsite@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    category = make_category(db, restaurant.id)
    product = make_product(db, restaurant.id, category.id, price=10.0)
    return {"user": user, "restaurant": restaurant, "product": product}


def test_onsite_order_is_draft_by_default(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    p = setup["product"]

    res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": p.id, "quantity": 1}],
    })
    assert res.status_code == 201
    assert res.json()["is_draft"] is True
    assert res.json()["status"] == "pending"


def test_submit_onsite_order(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    p = setup["product"]
    u = setup["user"]
    headers = auth_headers(u.email)

    order_res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": p.id, "quantity": 1}],
    })
    order_id = order_res.json()["id"]

    submit_res = client.post(
        f"/restaurants/{r.id}/orders/{order_id}/submit",
        headers=headers,
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["is_draft"] is False


def test_cannot_submit_already_submitted_order(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    p = setup["product"]
    u = setup["user"]
    headers = auth_headers(u.email)

    order_res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": p.id, "quantity": 1}],
    })
    order_id = order_res.json()["id"]

    client.post(f"/restaurants/{r.id}/orders/{order_id}/submit", headers=headers)
    res = client.post(f"/restaurants/{r.id}/orders/{order_id}/submit", headers=headers)
    assert res.status_code == 400


def test_status_on_draft_without_hubrise_auto_submits(client: TestClient, db: Session, setup):
    """Sans Hubrise connecté, changer le status d'un draft le soumet automatiquement."""
    r = setup["restaurant"]
    p = setup["product"]
    u = setup["user"]

    order_res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": p.id, "quantity": 1}],
    })
    order_id = order_res.json()["id"]
    assert order_res.json()["is_draft"] is True

    res = client.post(
        f"/restaurants/{r.id}/orders/{order_id}/status",
        json={"status": "preparing"},
        headers=auth_headers(u.email),
    )
    # Sans Hubrise, le draft est auto-soumis et le status change
    assert res.status_code == 200
    assert res.json()["is_draft"] is False
    assert res.json()["status"] == "preparing"


def test_full_onsite_order_lifecycle(client: TestClient, db: Session, setup):
    """Draft → submit → preparing → completed."""
    r = setup["restaurant"]
    p = setup["product"]
    u = setup["user"]
    headers = auth_headers(u.email)

    order_id = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": p.id, "quantity": 2}],
    }).json()["id"]

    client.post(f"/restaurants/{r.id}/orders/{order_id}/submit", headers=headers)

    res = client.post(f"/restaurants/{r.id}/orders/{order_id}/status",
                      json={"status": "preparing"}, headers=headers)
    assert res.json()["status"] == "preparing"

    res = client.post(f"/restaurants/{r.id}/orders/{order_id}/status",
                      json={"status": "completed"}, headers=headers)
    assert res.json()["status"] == "completed"
    assert res.json()["completed_at"] is not None


def test_delete_draft_allowed_delete_submitted_not(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    p = setup["product"]
    u = setup["user"]
    headers = auth_headers(u.email)

    # Draft → supprimable
    order_id = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": p.id, "quantity": 1}],
    }).json()["id"]
    res = client.delete(f"/restaurants/{r.id}/orders/{order_id}", headers=headers)
    assert res.status_code == 204

    # Submitted → non supprimable
    order_id2 = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": p.id, "quantity": 1}],
    }).json()["id"]
    client.post(f"/restaurants/{r.id}/orders/{order_id2}/submit", headers=headers)
    res = client.delete(f"/restaurants/{r.id}/orders/{order_id2}", headers=headers)
    assert res.status_code == 400
