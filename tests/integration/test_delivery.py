"""Tests d'intégration — livraison : tiers, calcul des frais, commandes delivery."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.integration.conftest import make_user, make_restaurant, make_category, make_product, auth_headers
from app.models.delivery_tiers import DeliveryTier
from app.models.restaurant_config import RestaurantConfig
from app.services.geo_service import geocode_address_sync


@pytest.fixture()
def setup(db: Session):
    user = make_user(db, email="owner_delivery@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    category = make_category(db, restaurant.id)
    product = make_product(db, restaurant.id, category.id, price=20.0)

    # Activer la livraison dans la config
    config = db.query(RestaurantConfig).filter_by(restaurant_id=restaurant.id).first()
    config.pickup = True
    config.max_delivery_km = 10
    db.commit()

    # Ajouter des tiers de livraison
    tiers = [
        DeliveryTier(restaurant_id=restaurant.id, min_km=0, max_km=3, price=2.5, min_order_amount=0),
        DeliveryTier(restaurant_id=restaurant.id, min_km=3, max_km=7, price=4.0, min_order_amount=15),
        DeliveryTier(restaurant_id=restaurant.id, min_km=7, max_km=10, price=6.0, min_order_amount=25),
    ]
    for tier in tiers:
        db.add(tier)
    db.commit()
    db.refresh(restaurant)

    return {"user": user, "restaurant": restaurant, "product": product}


def test_delivery_tier_applied_correctly(client: TestClient, db: Session, setup):
    """Commande delivery à 1.5km → tier 0-3km → frais 2.50."""
    r = setup["restaurant"]
    p = setup["product"]

    with patch("app.services.order_service.geocode_address_sync") as mock_geo, \
         patch("app.services.geo_service.geocode_address_sync") as mock_geo2:
        # Restaurant à Paris, client à 1.5km (~0.013° lat)
        mock_geo.side_effect = [
            {"lat": 48.8566, "lng": 2.3522},   # restaurant
            {"lat": 48.8696, "lng": 2.3522},   # client (~1.5km)
        ]
        mock_geo2.side_effect = mock_geo.side_effect

        order_res = client.post(f"/restaurants/{r.id}/orders", json={
            "type": "delivery",
            "items": [{"product_id": p.id, "quantity": 1}],
            "customer": {"first_name": "Jane", "last_name": "Doe", "phone": "+33600000020"},
            "address": {"street": "10 Rue Test", "city": "Paris", "postal_code": "75002", "country": "FR"},
        })

    assert order_res.status_code == 201
    data = order_res.json()
    assert data["type"] == "delivery"
    assert float(data["delivery_fee"]) == pytest.approx(2.50)
    assert float(data["items_subtotal"]) == pytest.approx(20.0)


def test_delivery_fee_higher_for_distant_address(client: TestClient, db: Session, setup):
    """Commande à 5km → tier 3-7km → frais 4.00."""
    r = setup["restaurant"]
    p = setup["product"]

    with patch("app.services.order_service.geocode_address_sync") as mock_geo:
        mock_geo.side_effect = [
            {"lat": 48.8566, "lng": 2.3522},
            {"lat": 48.9015, "lng": 2.3522},   # ~5km
        ]
        order_res = client.post(f"/restaurants/{r.id}/orders", json={
            "type": "delivery",
            "items": [{"product_id": p.id, "quantity": 1}],
            "customer": {"first_name": "Jane", "last_name": "Doe", "phone": "+33600000021"},
            "address": {"street": "10 Rue Test", "city": "Paris", "postal_code": "75018", "country": "FR"},
        })

    assert order_res.status_code == 201
    assert float(order_res.json()["delivery_fee"]) == pytest.approx(4.00)


def test_delivery_quote_eligible(client: TestClient, db: Session, setup):
    """Quote de livraison : adresse éligible."""
    r = setup["restaurant"]

    with patch("app.services.order_service.geocode_address_sync") as mock_geo, \
         patch("app.services.geo_service.geocode_address_sync") as mock_geo2:
        mock_geo.side_effect = [
            {"lat": 48.8566, "lng": 2.3522},
            {"lat": 48.8696, "lng": 2.3522},
        ]
        mock_geo2.side_effect = mock_geo.side_effect

        res = client.post(f"/restaurants/{r.id}/delivery/quote", json={
            "address": {"street": "10 Rue Test", "city": "Paris", "postal_code": "75002", "country": "FR"},
            "items_subtotal": "20.00",
        })

    assert res.status_code == 200
    data = res.json()
    assert data["eligible"] is True
    assert float(data["delivery_fee"]) == pytest.approx(2.50)


def test_delivery_quote_out_of_zone(client: TestClient, db: Session, setup):
    """Quote : adresse trop loin → non éligible."""
    r = setup["restaurant"]

    with patch("app.services.order_service.geocode_address_sync") as mock_geo, \
         patch("app.services.geo_service.geocode_address_sync") as mock_geo2:
        mock_geo.side_effect = [
            {"lat": 48.8566, "lng": 2.3522},
            {"lat": 48.9900, "lng": 2.3522},   # ~15km
        ]
        mock_geo2.side_effect = mock_geo.side_effect

        res = client.post(f"/restaurants/{r.id}/delivery/quote", json={
            "address": {"street": "10 Rue Loin", "city": "Versailles", "postal_code": "78000", "country": "FR"},
            "items_subtotal": "20.00",
        })

    assert res.status_code == 200
    assert res.json()["eligible"] is False


def test_geocode_address_sync_falls_back_to_structured_queries():
    responses = [
        [],
        [{
            "lat": "48.9584",
            "lon": "2.6044",
            "display_name": "Avenue La Martine, 77290 Mitry-Mory, France",
        }],
    ]

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params, headers, timeout):
            return FakeResponse(responses.pop(0))

    with patch("app.services.geo_service.httpx.Client", return_value=FakeClient()):
        result = geocode_address_sync({
            "street": "Avenue la martine",
            "city": "Mitry-Mory",
            "postal_code": "77290",
            "country": "France",
        })

    assert result["lat"] == pytest.approx(48.9584)
    assert result["lng"] == pytest.approx(2.6044)
    assert "Mitry-Mory" in result["place_name"]


def test_delivery_order_is_accepted_when_address_cannot_be_geocoded(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    p = setup["product"]

    with patch("app.services.order_service.geocode_address_sync", side_effect=ValueError("Adresse introuvable : adresse libre")):
        order_res = client.post(f"/restaurants/{r.id}/orders", json={
            "type": "delivery",
            "items": [{"product_id": p.id, "quantity": 1}],
            "customer": {"first_name": "Jane", "last_name": "Doe", "phone": "+33600000022"},
            "address": {
                "street": "Adresse tapée librement",
                "city": "Mitry-Mory",
                "postal_code": "77290",
                "country": "France",
            },
        })

    assert order_res.status_code == 201
    data = order_res.json()
    assert data["type"] == "delivery"
    assert float(data["delivery_fee"]) == pytest.approx(0.0)
    assert data["delivery_distance_km"] is None
    assert float(data["amount_total"]) == pytest.approx(20.0)
