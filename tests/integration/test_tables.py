"""Tests d'intégration — tables."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.integration.conftest import make_user, make_restaurant, make_category, make_product, auth_headers


@pytest.fixture()
def setup(db: Session):
    user = make_user(db, email="owner_tables@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    return {"user": user, "restaurant": restaurant}


def test_create_and_list_tables(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    res = client.post(f"/restaurants/{r.id}/tables", json={
        "table_number": "T1",
        "number_of_people": 4,
        "is_available": True,
        "location": "salle principale",
    }, headers=headers)
    assert res.status_code == 201
    assert res.json()["table_number"] == "T1"

    res = client.get(f"/restaurants/{r.id}/tables", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_update_table(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    created = client.post(f"/restaurants/{r.id}/tables", json={
        "table_number": "T2", "number_of_people": 2,
    }, headers=headers)
    table_id = created.json()["id"]

    res = client.put(f"/restaurants/{r.id}/tables/{table_id}", json={
        "number_of_people": 6, "is_available": False,
    }, headers=headers)
    assert res.status_code == 200
    assert res.json()["number_of_people"] == 6
    assert res.json()["is_available"] is False


def test_delete_table(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    created = client.post(f"/restaurants/{r.id}/tables", json={
        "table_number": "T3", "number_of_people": 2,
    }, headers=headers)
    table_id = created.json()["id"]

    res = client.delete(f"/restaurants/{r.id}/tables/{table_id}", headers=headers)
    assert res.status_code == 204

    res = client.get(f"/restaurants/{r.id}/tables/{table_id}", headers=headers)
    assert res.status_code == 404


def test_onsite_order_marks_table_available_on_complete(client: TestClient, db: Session, setup):
    """Quand une commande onsite est complétée, la table doit redevenir disponible."""
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    # Créer table indisponible
    table_res = client.post(f"/restaurants/{r.id}/tables", json={
        "table_number": "T4", "number_of_people": 4, "is_available": False,
    }, headers=headers)
    table_id = table_res.json()["id"]

    category = make_category(db, r.id)
    product = make_product(db, r.id, category.id)

    # Créer commande onsite liée à la table
    order_res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "onsite",
        "table_id": table_id,
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]

    # Compléter la commande
    client.post(
        f"/restaurants/{r.id}/orders/{order_id}/status",
        json={"status": "completed"},
        headers=headers,
    )

    # La table doit être disponible
    table_check = client.get(f"/restaurants/{r.id}/tables/{table_id}", headers=headers)
    assert table_check.json()["is_available"] is True
