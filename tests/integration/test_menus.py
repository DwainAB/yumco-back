"""Tests d'intégration — menus avec catégories et options."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.integration.conftest import make_user, make_restaurant, auth_headers


@pytest.fixture()
def setup(db: Session):
    user = make_user(db, email="owner_menus@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    return {"user": user, "restaurant": restaurant}


def _menu_payload(**overrides):
    base = {
        "name": "Menu Midi",
        "price": "15.50",
        "is_available": True,
        "available_online": True,
        "available_onsite": True,
        "categories": [
            {
                "name": "Entrée",
                "max_options": 1,
                "is_required": True,
                "display_order": 0,
                "options": [
                    {"name": "Salade", "additional_price": "0.00", "display_order": 0},
                    {"name": "Soupe", "additional_price": "1.50", "display_order": 1},
                ],
            },
            {
                "name": "Plat",
                "max_options": 1,
                "is_required": True,
                "display_order": 1,
                "options": [
                    {"name": "Poulet", "additional_price": "0.00", "display_order": 0},
                    {"name": "Poisson", "additional_price": "2.00", "display_order": 1},
                ],
            },
        ],
    }
    base.update(overrides)
    return base


def test_create_menu_with_categories(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    res = client.post(f"/restaurants/{r.id}/menus", json=_menu_payload(), headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Menu Midi"
    assert float(data["price"]) == pytest.approx(15.50)
    assert len(data["categories"]) == 2
    assert len(data["categories"][0]["options"]) == 2


def test_list_menus(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    client.post(f"/restaurants/{r.id}/menus", json=_menu_payload(name="Menu A"), headers=headers)
    client.post(f"/restaurants/{r.id}/menus", json=_menu_payload(name="Menu B"), headers=headers)

    res = client.get(f"/restaurants/{r.id}/menus")
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_get_menu(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    created = client.post(f"/restaurants/{r.id}/menus", json=_menu_payload(), headers=headers)
    menu_id = created.json()["id"]

    res = client.get(f"/restaurants/{r.id}/menus/{menu_id}")
    assert res.status_code == 200
    assert res.json()["id"] == menu_id


def test_update_menu(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    created = client.post(f"/restaurants/{r.id}/menus", json=_menu_payload(), headers=headers)
    menu_id = created.json()["id"]

    res = client.put(f"/restaurants/{r.id}/menus/{menu_id}", json={
        "name": "Menu Soir",
        "price": "22.00",
        "is_available": False,
    }, headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Menu Soir"
    assert float(res.json()["price"]) == pytest.approx(22.00)
    assert res.json()["is_available"] is False


def test_delete_menu(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    created = client.post(f"/restaurants/{r.id}/menus", json=_menu_payload(), headers=headers)
    menu_id = created.json()["id"]

    res = client.delete(f"/restaurants/{r.id}/menus/{menu_id}", headers=headers)
    assert res.status_code == 204

    res = client.get(f"/restaurants/{r.id}/menus/{menu_id}")
    assert res.status_code == 404


def test_order_with_menu_and_option(client: TestClient, db: Session, setup):
    """Commande avec menu + option — vérifie que le prix inclut le supplément."""
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    created = client.post(f"/restaurants/{r.id}/menus", json=_menu_payload(), headers=headers)
    menu = created.json()
    menu_id = menu["id"]
    # Option "Soupe" (supplément 1.50) dans la catégorie Entrée
    soupe_option_id = menu["categories"][0]["options"][1]["id"]

    order_res = client.post(f"/restaurants/{r.id}/orders", json={
        "type": "pickup",
        "items": [{
            "menu_id": menu_id,
            "quantity": 1,
            "selected_options": [soupe_option_id],
        }],
        "customer": {"first_name": "Jane", "last_name": "Doe", "phone": "+33600000010"},
    })
    assert order_res.status_code == 201
    data = order_res.json()
    # Prix = 15.50 (menu) + 1.50 (soupe) = 17.00
    assert float(data["items_subtotal"]) == pytest.approx(17.00)
