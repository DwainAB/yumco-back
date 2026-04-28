"""Tests d'intégration — réservations."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.integration.conftest import make_user, make_restaurant, auth_headers


@pytest.fixture()
def setup(db: Session):
    user = make_user(db, email="owner_res@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    return {"user": user, "restaurant": restaurant}


def _reservation_payload(**overrides):
    base = {
        "full_name": "Jean Dupont",
        "phone": "+33600000001",
        "email": "jean@test.com",
        "number_of_people": 4,
        "reservation_date": "2026-06-15",
        "reservation_time": "19:30:00",
        "comment": "Table fenêtre",
    }
    base.update(overrides)
    return base


def test_create_reservation(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    res = client.post(f"/restaurants/{r.id}/reservations", json=_reservation_payload())
    assert res.status_code == 201
    data = res.json()
    assert data["full_name"] == "Jean Dupont"
    assert data["number_of_people"] == 4
    assert data["status"] == "pending"


def test_list_reservations(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    client.post(f"/restaurants/{r.id}/reservations", json=_reservation_payload())
    client.post(f"/restaurants/{r.id}/reservations", json=_reservation_payload(full_name="Marie Martin", phone="+33600000002"))

    res = client.get(f"/restaurants/{r.id}/reservations", headers=auth_headers(u.email))
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_get_reservation(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    created = client.post(f"/restaurants/{r.id}/reservations", json=_reservation_payload())
    reservation_id = created.json()["id"]

    res = client.get(f"/restaurants/{r.id}/reservations/{reservation_id}", headers=auth_headers(u.email))
    assert res.status_code == 200
    assert res.json()["id"] == reservation_id


def test_update_reservation_status(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    created = client.post(f"/restaurants/{r.id}/reservations", json=_reservation_payload())
    reservation_id = created.json()["id"]

    res = client.patch(
        f"/restaurants/{r.id}/reservations/{reservation_id}",
        json={"status": "confirmed"},
        headers=auth_headers(u.email),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "confirmed"


def test_update_reservation_details(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    created = client.post(f"/restaurants/{r.id}/reservations", json=_reservation_payload())
    reservation_id = created.json()["id"]

    res = client.put(
        f"/restaurants/{r.id}/reservations/{reservation_id}",
        json={"number_of_people": 6, "comment": "Anniversaire"},
        headers=auth_headers(u.email),
    )
    assert res.status_code == 200
    assert res.json()["number_of_people"] == 6
    assert res.json()["comment"] == "Anniversaire"


def test_delete_reservation(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    created = client.post(f"/restaurants/{r.id}/reservations", json=_reservation_payload())
    reservation_id = created.json()["id"]

    res = client.delete(f"/restaurants/{r.id}/reservations/{reservation_id}", headers=auth_headers(u.email))
    assert res.status_code == 204

    res = client.get(f"/restaurants/{r.id}/reservations/{reservation_id}", headers=auth_headers(u.email))
    assert res.status_code == 404


def test_reservation_not_found(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    res = client.get(f"/restaurants/{r.id}/reservations/99999", headers=auth_headers(u.email))
    assert res.status_code == 404
