"""Tests d'intégration — restaurants, catégories, produits."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.integration.conftest import (
    make_user, make_restaurant, make_category, make_product, auth_headers
)


def test_get_restaurant(client: TestClient, db: Session):
    """GET /restaurants/{id} est public — n'importe qui peut le lire."""
    owner = make_user(db, email="owner_r1@test.com")
    restaurant = make_restaurant(db, owner_id=owner.id, name="Mon Restaurant")

    res = client.get(f"/restaurants/{restaurant.id}", headers=auth_headers(owner.email))
    assert res.status_code == 200
    assert res.json()["name"] == "Mon Restaurant"


def test_get_restaurant_not_found(client: TestClient, db: Session):
    res = client.get("/restaurants/99999", headers=auth_headers("nobody@test.com"))
    assert res.status_code == 404


def test_create_restaurant_requires_admin(client: TestClient, db: Session):
    """POST /restaurants/ est réservé aux admins."""
    user = make_user(db, email="owner_r2@test.com", is_admin=False)
    res = client.post("/restaurants/", json={
        "name": "Resto",
        "email": "resto@test.com",
        "phone": "+33100000002",
        "timezone": "Europe/Paris",
        "address": {"street": "2 Rue", "city": "Lyon", "postal_code": "69001", "country": "FR"},
    }, headers=auth_headers(user.email))
    assert res.status_code == 403


def test_admin_can_create_restaurant(client: TestClient, db: Session):
    admin = make_user(db, email="admin_r@test.com", is_admin=True)
    res = client.post("/restaurants/", json={
        "name": "Admin Resto",
        "email": "adminresto@test.com",
        "phone": "+33100000003",
        "timezone": "Europe/Paris",
        "address": {"street": "3 Rue", "city": "Paris", "postal_code": "75001", "country": "FR"},
    }, headers=auth_headers(admin.email))
    assert res.status_code == 201
    assert res.json()["name"] == "Admin Resto"


def test_create_restaurant_rejects_overlapping_delivery_tier_boundaries(client: TestClient, db: Session):
    admin = make_user(db, email="admin_delivery_overlap@test.com", is_admin=True)
    res = client.post("/restaurants/", json={
        "name": "Overlap Resto",
        "email": "overlapresto@test.com",
        "phone": "+33100000013",
        "address": {"street": "13 Rue", "city": "Paris", "postal_code": "75013", "country": "FR"},
        "delivery_tiers": [
            {"min_km": 0, "max_km": 10, "price": "4.00", "min_order_amount": "0.00"},
            {"min_km": 10, "max_km": 15, "price": "6.00", "min_order_amount": "0.00"},
        ],
    }, headers=auth_headers(admin.email))
    assert res.status_code == 422
    assert "must not overlap or share a boundary" in str(res.json())


def test_create_restaurant_allows_stacked_delivery_pricing_on_same_range(client: TestClient, db: Session):
    admin = make_user(db, email="admin_delivery_stack@test.com", is_admin=True)
    res = client.post("/restaurants/", json={
        "name": "Stacked Resto",
        "email": "stackedresto@test.com",
        "phone": "+33100000014",
        "address": {"street": "14 Rue", "city": "Paris", "postal_code": "75014", "country": "FR"},
        "delivery_tiers": [
            {"min_km": 0, "max_km": 10, "price": "4.00", "min_order_amount": "0.00"},
            {"min_km": 0, "max_km": 10, "price": "0.00", "min_order_amount": "25.00"},
        ],
    }, headers=auth_headers(admin.email))
    assert res.status_code == 201
    assert len(res.json()["delivery_tiers"]) == 2


def test_update_restaurant(client: TestClient, db: Session):
    """N'importe quel user authentifié peut mettre à jour (pas de garde dans la route)."""
    owner = make_user(db, email="owner_r3@test.com")
    restaurant = make_restaurant(db, owner_id=owner.id)

    res = client.put(f"/restaurants/{restaurant.id}", json={"name": "Nouveau Nom"},
                     headers=auth_headers(owner.email))
    assert res.status_code == 200
    assert res.json()["name"] == "Nouveau Nom"


def test_create_category_and_product(client: TestClient, db: Session):
    owner = make_user(db, email="owner_r4@test.com")
    restaurant = make_restaurant(db, owner_id=owner.id)
    headers = auth_headers(owner.email)

    res = client.post(f"/restaurants/{restaurant.id}/categories", json={"name": "Pizzas"}, headers=headers)
    assert res.status_code == 201
    cat_id = res.json()["id"]

    res = client.post(f"/restaurants/{restaurant.id}/products", data={
        "name": "Margherita",
        "price": "11.50",
        "category_id": str(cat_id),
        "group": "main",
        "is_available": "true",
        "available_online": "true",
        "available_onsite": "true",
    }, headers=headers)
    assert res.status_code == 201
    assert res.json()["name"] == "Margherita"
    assert float(res.json()["price"]) == pytest.approx(11.50)


def test_list_products(client: TestClient, db: Session):
    owner = make_user(db, email="owner_r5@test.com")
    restaurant = make_restaurant(db, owner_id=owner.id)
    category = make_category(db, restaurant.id)
    make_product(db, restaurant.id, category.id, "Burger", 12.5)
    make_product(db, restaurant.id, category.id, "Frites", 4.0)

    res = client.get(f"/restaurants/{restaurant.id}/products", headers=auth_headers(owner.email))
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_delete_product(client: TestClient, db: Session):
    owner = make_user(db, email="owner_r6@test.com")
    restaurant = make_restaurant(db, owner_id=owner.id)
    category = make_category(db, restaurant.id)
    product = make_product(db, restaurant.id, category.id)
    headers = auth_headers(owner.email)

    res = client.delete(f"/restaurants/{restaurant.id}/products/{product.id}", headers=headers)
    assert res.status_code == 204

    res = client.get(f"/restaurants/{restaurant.id}/products", headers=headers)
    assert all(p["id"] != product.id for p in res.json())
