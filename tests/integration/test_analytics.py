"""Tests d'intégration — analytics (orders, revenue, performance, customers)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.integration.conftest import make_user, make_restaurant, make_category, make_product, auth_headers


@pytest.fixture()
def setup(db: Session):
    user = make_user(db, email="owner_analytics@test.com")
    restaurant = make_restaurant(db, owner_id=user.id)
    category = make_category(db, restaurant.id)
    product = make_product(db, restaurant.id, category.id, price=15.0)
    return {"user": user, "restaurant": restaurant, "product": product}


def _create_order(client, restaurant_id, product_id, qty=1, phone="+33600000050"):
    return client.post(f"/restaurants/{restaurant_id}/orders", json={
        "type": "pickup",
        "items": [{"product_id": product_id, "quantity": qty}],
        "customer": {"first_name": "Test", "last_name": "Client", "phone": phone},
    })


def test_order_analytics_returns_valid_structure(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    p = setup["product"]

    _create_order(client, r.id, p.id)

    res = client.get(f"/restaurants/{r.id}/orders/analytics", headers=auth_headers(u.email))
    assert res.status_code == 200
    data = res.json()
    assert "top_items" in data
    assert "monthly_orders_count" in data
    assert "delivery_percentage" in data
    assert "pickup_percentage" in data


def test_revenue_analytics_returns_valid_structure(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    p = setup["product"]

    _create_order(client, r.id, p.id, qty=2)

    res = client.get(f"/restaurants/{r.id}/revenue/analytics", headers=auth_headers(u.email))
    assert res.status_code == 200
    data = res.json()
    assert "current_month_amount" in data
    assert "yearly_channels" in data
    assert "best_month" in data


def test_performance_analytics_returns_valid_structure(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]

    res = client.get(f"/restaurants/{r.id}/performance/analytics", headers=auth_headers(u.email))
    assert res.status_code == 200
    data = res.json()
    assert "preparation_time" in data
    assert "average_minutes" in data["preparation_time"]
    assert "preparers" in data


def test_customer_analytics_returns_valid_structure(client: TestClient, db: Session, setup):
    r = setup["restaurant"]
    u = setup["user"]
    p = setup["product"]

    _create_order(client, r.id, p.id, phone="+33600000051")
    _create_order(client, r.id, p.id, phone="+33600000052")

    res = client.get(f"/restaurants/{r.id}/customers/analytics", headers=auth_headers(u.email))
    assert res.status_code == 200
    data = res.json()
    assert "total_customers" in data
    assert "loyal_customers" in data
    assert "top_customers" in data


def test_analytics_without_orders(client: TestClient, db: Session, setup):
    """Analytics sur un restaurant vide — ne doit pas crasher."""
    r = setup["restaurant"]
    u = setup["user"]
    headers = auth_headers(u.email)

    res = client.get(f"/restaurants/{r.id}/orders/analytics", headers=headers)
    assert res.status_code == 200

    res = client.get(f"/restaurants/{r.id}/revenue/analytics", headers=headers)
    assert res.status_code == 200

    res = client.get(f"/restaurants/{r.id}/performance/analytics", headers=headers)
    assert res.status_code == 200
