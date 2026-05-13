from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_create_order_unknown_restaurant_returns_404(client: TestClient, db: Session):
    response = client.post(
        "/restaurants/999999/orders",
        json={
            "type": "pickup",
            "items": [{"product_id": 1, "quantity": 1}],
            "customer": {
                "first_name": "Jane",
                "last_name": "Doe",
                "phone": "+33600000001",
                "email": "jane@test.com",
            },
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Restaurant not found"
