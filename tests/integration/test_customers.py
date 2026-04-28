"""Tests d'intégration — customers."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.integration.conftest import make_user, make_restaurant, make_category, make_product, auth_headers


@pytest.fixture()
def setup(db: Session):
    user = make_user(db, email="owner_customers@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    category = make_category(db, restaurant.id)
    product = make_product(db, restaurant.id, category.id, price=10.0)
    return {"user": user, "restaurant": restaurant, "product": product}


def _create_order_with_customer(client, restaurant_id, product_id, phone, email=None):
    payload = {
        "type": "pickup",
        "items": [{"product_id": product_id, "quantity": 1}],
        "customer": {"first_name": "Jane", "last_name": "Doe", "phone": phone},
    }
    if email:
        payload["customer"]["email"] = email
    return client.post(f"/restaurants/{restaurant_id}/orders", json=payload)


def test_customer_created_on_first_order(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    p = setup["product"]

    _create_order_with_customer(client, r.id, p.id, "+33600000060")

    res = client.get(f"/restaurants/{r.id}/customers", headers=auth_headers(u.email))
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["phone"] == "+33600000060"


def test_each_order_creates_a_customer(client: TestClient, db: Session, setup):
    """Chaque commande crée un customer (pas de déduplication par téléphone pour l'instant)."""
    r = setup["restaurant"]
    u = setup["user"]
    p = setup["product"]

    _create_order_with_customer(client, r.id, p.id, "+33600000061")
    _create_order_with_customer(client, r.id, p.id, "+33600000061")

    res = client.get(f"/restaurants/{r.id}/customers", headers=auth_headers(u.email))
    assert len(res.json()) == 2


def test_get_customer(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    p = setup["product"]

    _create_order_with_customer(client, r.id, p.id, "+33600000062")
    customers = client.get(f"/restaurants/{r.id}/customers", headers=auth_headers(u.email)).json()
    customer_id = customers[0]["id"]

    res = client.get(f"/restaurants/{r.id}/customers/{customer_id}", headers=auth_headers(u.email))
    assert res.status_code == 200
    assert res.json()["id"] == customer_id


def test_update_customer(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    p = setup["product"]
    headers = auth_headers(u.email)

    _create_order_with_customer(client, r.id, p.id, "+33600000063")
    customer_id = client.get(f"/restaurants/{r.id}/customers", headers=headers).json()[0]["id"]

    res = client.put(f"/restaurants/{r.id}/customers/{customer_id}",
                     json={"first_name": "Marie", "last_name": "Martin"},
                     headers=headers)
    assert res.status_code == 200
    assert res.json()["first_name"] == "Marie"


def test_delete_customer(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    p = setup["product"]
    headers = auth_headers(u.email)

    _create_order_with_customer(client, r.id, p.id, "+33600000064")
    customer_id = client.get(f"/restaurants/{r.id}/customers", headers=headers).json()[0]["id"]

    res = client.delete(f"/restaurants/{r.id}/customers/{customer_id}", headers=headers)
    assert res.status_code == 204

    res = client.get(f"/restaurants/{r.id}/customers", headers=headers)
    assert all(c["id"] != customer_id for c in res.json())
