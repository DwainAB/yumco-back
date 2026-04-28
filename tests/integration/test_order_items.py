"""Tests d'intégration — ajout/suppression d'articles dans une commande existante."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.integration.conftest import make_user, make_restaurant, make_category, make_product, auth_headers


@pytest.fixture()
def setup(db: Session):
    user = make_user(db, email="owner_items@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    category = make_category(db, restaurant.id)
    product_a = make_product(db, restaurant.id, category.id, name="Burger", price=12.0)
    product_b = make_product(db, restaurant.id, category.id, name="Frites", price=4.0)
    return {"user": user, "restaurant": restaurant, "product_a": product_a, "product_b": product_b}


def test_add_item_to_existing_order(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    pa = setup["product_a"]
    pb = setup["product_b"]
    headers = auth_headers(u.email)

    # Commande initiale avec 1 burger
    order_res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": pa.id, "quantity": 1}],
    })
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]
    assert float(order_res.json()["items_subtotal"]) == pytest.approx(12.0)

    # Ajouter des frites
    add_res = client.post(
        f"/restaurants/{r.id}/orders/{order_id}/items",
        json=[{"product_id": pb.id, "quantity": 2}],
        headers=headers,
    )
    assert add_res.status_code == 200
    assert float(add_res.json()["items_subtotal"]) == pytest.approx(20.0)  # 12 + 4*2


def test_add_same_product_increments_quantity(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    pa = setup["product_a"]
    headers = auth_headers(u.email)

    order_res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": pa.id, "quantity": 1}],
    })
    order_id = order_res.json()["id"]

    # Ajouter encore 1 burger → doit incrémenter
    add_res = client.post(
        f"/restaurants/{r.id}/orders/{order_id}/items",
        json=[{"product_id": pa.id, "quantity": 1}],
        headers=headers,
    )
    assert add_res.status_code == 200
    items = add_res.json()["items"]
    burger_item = next(i for i in items if i["product_id"] == pa.id and i["parent_order_item_id"] is None)
    assert burger_item["quantity"] == 2
    assert float(add_res.json()["items_subtotal"]) == pytest.approx(24.0)


def test_remove_item_decrements_quantity(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    pa = setup["product_a"]
    headers = auth_headers(u.email)

    order_res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": pa.id, "quantity": 3}],
    })
    order_id = order_res.json()["id"]
    item_id = order_res.json()["items"][0]["id"]

    # Supprimer 1 unité
    del_res = client.delete(
        f"/restaurants/{r.id}/orders/{order_id}/items/{item_id}",
        headers=headers,
    )
    assert del_res.status_code == 200
    items = del_res.json()["items"]
    burger_item = next(i for i in items if i["id"] == item_id)
    assert burger_item["quantity"] == 2
    assert float(del_res.json()["items_subtotal"]) == pytest.approx(24.0)


def test_remove_last_unit_deletes_item(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    pa = setup["product_a"]
    pb = setup["product_b"]
    headers = auth_headers(u.email)

    order_res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [
            {"product_id": pa.id, "quantity": 1},
            {"product_id": pb.id, "quantity": 1},
        ],
    })
    order_id = order_res.json()["id"]
    frites_item = next(i for i in order_res.json()["items"] if i["product_id"] == pb.id)
    frites_id = frites_item["id"]

    del_res = client.delete(
        f"/restaurants/{r.id}/orders/{order_id}/items/{frites_id}",
        headers=headers,
    )
    assert del_res.status_code == 200
    remaining_ids = [i["id"] for i in del_res.json()["items"]]
    assert frites_id not in remaining_ids
    assert float(del_res.json()["items_subtotal"]) == pytest.approx(12.0)


def test_add_invalid_product_returns_400(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    pa = setup["product_a"]
    headers = auth_headers(u.email)

    order_res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "items": [{"product_id": pa.id, "quantity": 1}],
    })
    order_id = order_res.json()["id"]

    res = client.post(
        f"/restaurants/{r.id}/orders/{order_id}/items",
        json=[{"product_id": 99999, "quantity": 1}],
        headers=headers,
    )
    assert res.status_code == 400
