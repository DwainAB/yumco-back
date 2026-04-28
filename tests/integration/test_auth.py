"""Tests d'intégration — authentification."""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.integration.conftest import make_user, make_restaurant, auth_headers


def test_login_success(client: TestClient, db: Session):
    make_user(db, email="login@test.com", password="password123")
    res = client.post("/auth/login", json={"email": "login@test.com", "password": "password123"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password(client: TestClient, db: Session):
    make_user(db, email="wrong@test.com", password="correct")
    res = client.post("/auth/login", json={"email": "wrong@test.com", "password": "bad"})
    assert res.status_code == 401


def test_get_me(client: TestClient, db: Session):
    make_user(db, email="me@test.com")
    res = client.get("/auth/me", headers=auth_headers("me@test.com"))
    assert res.status_code == 200
    assert res.json()["email"] == "me@test.com"


def test_get_me_without_token(client: TestClient, db: Session):
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_register_staff_as_admin(client: TestClient, db: Session):
    """Un admin peut créer un staff pour un restaurant via /auth/register."""
    admin = make_user(db, email="admin@test.com", is_admin=True)
    restaurant = make_restaurant(db, owner_id=admin.id)

    # register requiert restaurant_id ET role ensemble
    res = client.post("/auth/register", json={
        "email": "staff@test.com",
        "password": "password123",
        "first_name": "Jean",
        "last_name": "Dupont",
        "phone": "+33600000099",
        "restaurant_id": restaurant.id,
        "role": "manager",
    }, headers=auth_headers("admin@test.com"))
    assert res.status_code == 201
    assert res.json()["email"] == "staff@test.com"


def test_register_duplicate_email_rejected(client: TestClient, db: Session):
    admin = make_user(db, email="admin2@test.com", is_admin=True)
    restaurant = make_restaurant(db, owner_id=admin.id)
    make_user(db, email="dup@test.com")

    res = client.post("/auth/register", json={
        "email": "dup@test.com",
        "password": "password123",
        "first_name": "Jean",
        "last_name": "Dupont",
        "phone": "+33600000088",
        "restaurant_id": restaurant.id,
        "role": "manager",
    }, headers=auth_headers("admin2@test.com"))
    assert res.status_code == 400
