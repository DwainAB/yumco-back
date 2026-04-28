from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
import inspect
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.security import hash_password
from app.db.database import get_db
from app.core.security import get_current_user
from main import app


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class DummyEntity:
    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)

    def __getattr__(self, name: str) -> Any:
        defaults = {
            "id": 1,
            "user_id": 1,
            "restaurant_id": 1,
            "category_id": 1,
            "product_id": 1,
            "menu_id": 1,
            "table_id": 1,
            "order_id": 1,
            "reservation_id": 1,
            "customer_id": 1,
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "phone": "+33123456789",
            "name": "Sample",
            "description": "Sample description",
            "street": "1 Rue de Test",
            "city": "Paris",
            "postal_code": "75001",
            "country": "FR",
            "timezone": "Europe/Paris",
            "type": "pickup",
            "status": "pending",
            "group": "main",
            "role": "owner",
            "subscription_plan": "starter",
            "subscription_interval": "month",
            "subscription_status": "active",
            "subscription_display_status": "active",
            "stripe_id": "acct_123",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "hubrise_account_id": "hub_acc",
            "hubrise_location_id": "hub_loc",
            "token_type": "bearer",
            "scope": "orders",
            "order_number": "ORD-001",
            "notes": "notes",
            "image_url": "https://example.com/image.png",
            "expo_push_token": "ExponentPushToken[test]",
            "platform": "ios",
            "device_name": "iPhone",
            "hashed_password": hash_password("string"),
            "created_at": NOW,
            "updated_at": NOW,
            "completed_at": NOW,
            "last_seen_at": NOW,
            "subscription_current_period_ends_at": NOW,
            "subscription_next_billing_at": NOW,
            "ai_cycle_started_at": NOW,
            "last_hubrise_synced_at": NOW,
            "is_admin": True,
            "is_active": True,
            "is_deleted": False,
            "is_closed": False,
            "is_available": True,
            "available_online": True,
            "available_onsite": True,
            "payment_online": False,
            "payment_onsite": True,
            "notify_orders": True,
            "notify_reservations": True,
            "has_tablet_rental": False,
            "has_printer_rental": False,
            "subscription_cancel_at_period_end": False,
            "stripe_charges_enabled": True,
            "stripe_payouts_enabled": True,
            "stripe_details_submitted": True,
            "connected": True,
            "asap": False,
            "url": "https://example.com",
            "checkout_url": "https://example.com/checkout",
            "checkout_session_id": "cs_test_123",
            "monthly_quota": 100,
            "usage_count": 1,
            "usage_remaining": 99,
            "monthly_token_quota": 10000,
            "token_usage_count": 100,
            "token_usage_remaining": 9900,
            "ai_monthly_quota": 100,
            "ai_usage_count": 1,
            "ai_monthly_token_quota": 10000,
            "ai_token_usage_count": 100,
            "is_ai_enabled": True,
            "is_quota_reached": False,
            "is_token_quota_reached": False,
            "max_delivery_km": 5,
            "price": Decimal("12.50"),
            "unit_price": Decimal("12.50"),
            "subtotal": Decimal("12.50"),
            "total": Decimal("15.00"),
            "delivery_fee": Decimal("2.50"),
            "service_fee": Decimal("0.00"),
            "items_subtotal": Decimal("12.50"),
            "quantity": 1,
            "people_count": 2,
            "day": 0,
            "lunch_open": "12:00:00",
            "lunch_close": "14:00:00",
            "dinner_open": "19:00:00",
            "dinner_close": "22:00:00",
            "address": DummyEntity(street="1 Rue de Test", city="Paris", postal_code="75001", country="FR"),
            "config": DummyEntity(
                id=1,
                restaurant_id=1,
                accept_orders=True,
                preparation_time=15,
                midday_delivery=True,
                evening_delivery=True,
                pickup=True,
                onsite=True,
                reservation=True,
                all_you_can_eat=False,
                a_la_carte=True,
                payment_online=False,
                payment_onsite=True,
                max_delivery_km=5,
            ),
            "roles": [DummyEntity(restaurant_id=1, type="owner")],
            "delivery_tiers": [],
            "opening_hours": [],
            "items": [],
            "slots": [],
            "messages": [],
            "allergens": [],
            "options": [],
        }
        if name in defaults:
            return defaults[name]
        if name.endswith("_id"):
            return 1
        if name.startswith("is_") or name.startswith("has_") or name.startswith("can_"):
            return False
        if name.endswith("_at"):
            return NOW
        if name.endswith("_url"):
            return "https://example.com"
        if name.endswith("_count"):
            return 0
        if name.endswith("_quota") or name.endswith("_remaining"):
            return 0
        if name in {"menus", "products", "categories", "customers", "orders", "reservations"}:
            return []
        return f"sample_{name}"


class QueryStub:
    def __init__(self, target: Any) -> None:
        self.target = target

    def filter(self, *args: Any, **kwargs: Any) -> "QueryStub":
        return self

    def order_by(self, *args: Any, **kwargs: Any) -> "QueryStub":
        return self

    def subquery(self) -> list[int]:
        return [1]

    def first(self) -> Any:
        return sample_for_target(self.target)

    def all(self) -> list[Any]:
        return [sample_for_target(self.target)]


class DummySession:
    def query(self, target: Any) -> QueryStub:
        return QueryStub(target)

    def add(self, value: Any) -> None:
        return None

    def delete(self, value: Any) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def refresh(self, value: Any) -> None:
        if getattr(value, "id", None) is None:
            setattr(value, "id", 1)
        if getattr(value, "created_at", None) is None:
            setattr(value, "created_at", NOW)
        if getattr(value, "restaurant_id", None) is None:
            setattr(value, "restaurant_id", 1)
        return None

    def close(self) -> None:
        return None


def sample_for_target(target: Any) -> Any:
    target_name = getattr(target, "__name__", None) or getattr(target, "key", None) or str(target)
    text = str(target_name).lower()

    if "restaurantconfig" in text:
        return DummyEntity(
            id=1,
            restaurant_id=1,
            accept_orders=True,
            preparation_time=15,
            midday_delivery=True,
            evening_delivery=True,
            pickup=True,
            onsite=True,
            reservation=True,
            all_you_can_eat=False,
            a_la_carte=True,
            payment_online=False,
            payment_onsite=True,
            max_delivery_km=5,
        )
    if "openinghours" in text:
        return DummyEntity(restaurant_id=1, day=0, is_closed=False, lunch_open="12:00:00", lunch_close="14:00:00", dinner_open="19:00:00", dinner_close="22:00:00")
    if "hubriseconnection" in text:
        return DummyEntity(restaurant_id=1, hubrise_location_id="hub_loc")
    if "hubriseorderlog" in text:
        return DummyEntity(
            id=1,
            status="sent",
            hubrise_location_id="hub_loc",
            request_payload={"items": []},
            response_payload={"status": "ok"},
            error_message=None,
            created_at=NOW,
            updated_at=NOW,
        )
    if "table" in text:
        return DummyEntity(
            id=1,
            restaurant_id=1,
            table_number="T1",
            number_of_people=4,
            is_available=True,
            location="main-room",
            temporary=False,
            created_at=NOW,
        )
    if "customer" in text:
        return DummyEntity(id=1, restaurant_id=1, first_name="Jane", last_name="Doe", phone="+33123456789", email="jane@example.com", created_at=NOW)
    if "reservation" in text:
        return DummyEntity(
            id=1,
            restaurant_id=1,
            full_name="Jane Doe",
            phone="+33123456789",
            email="jane@example.com",
            number_of_people=2,
            reservation_date=date(2026, 1, 1),
            reservation_time=time(19, 30),
            comment="Window seat",
            status="confirmed",
            created_at=NOW,
        )
    if "order" in text:
        return DummyEntity(
            id=1,
            restaurant_id=1,
            customer_id=1,
            order_number="ORD-001",
            type="pickup",
            status="pending",
            payment_status="paid",
            items_subtotal=12.5,
            total=Decimal("15.00"),
            amount_total=15.0,
            subtotal=Decimal("12.50"),
            delivery_fee=Decimal("2.50"),
            delivery_distance_km=1.8,
            service_fee=Decimal("0.00"),
            is_draft=False,
            requested_time=NOW,
            preparing_by=1,
            prepared_by_user=DummyEntity(id=1, first_name="Test", last_name="User", phone="+33123456789"),
            customer=DummyEntity(
                id=1,
                restaurant_id=1,
                first_name="Jane",
                last_name="Doe",
                email="jane@example.com",
                phone="+33123456789",
                created_at=NOW,
                updated_at=NOW,
            ),
            address=DummyEntity(street="1 Rue de Test", city="Paris", postal_code="75001", country="FR"),
            created_at=NOW,
            items=[],
            hubrise_order_id="hub_order_123",
            hubrise_raw_status="received",
            hubrise_sync_status="synced",
            hubrise_last_error=None,
            hubrise_synced_at=NOW,
        )
    if "menu" in text:
        return DummyEntity(id=1, restaurant_id=1, name="Lunch", created_at=NOW, categories=[])
    if "product" in text:
        return DummyEntity(
            id=1,
            restaurant_id=1,
            category_id=1,
            category=DummyEntity(id=1, name="Burgers"),
            name="Burger",
            price=Decimal("12.50"),
            description="Sample",
            is_available=True,
            available_online=True,
            available_onsite=True,
            group="main",
            allergens=[],
            image_url=None,
            created_at=NOW,
        )
    if "category" in text:
        return DummyEntity(id=1, restaurant_id=1, name="Burgers", created_at=NOW)
    if "role" in text:
        return DummyEntity(id=1, user_id=1, restaurant_id=1, type="owner")
    if "restaurant" in text:
        return DummyEntity(
            id=1,
            name="Yumco Test",
            email="restaurant@example.com",
            phone="+33123456789",
            timezone="Europe/Paris",
            address=DummyEntity(street="1 Rue de Test", city="Paris", postal_code="75001", country="FR"),
            stripe_id="acct_123",
            stripe_charges_enabled=True,
            stripe_payouts_enabled=True,
            stripe_details_submitted=True,
            subscription_plan="starter",
            subscription_interval="month",
            subscription_status="active",
            subscription_cancel_at_period_end=False,
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_123",
            has_tablet_rental=False,
            has_printer_rental=False,
            ai_monthly_quota=100,
            ai_usage_count=1,
            ai_monthly_token_quota=10000,
            ai_token_usage_count=100,
            ai_cycle_started_at=NOW,
            created_at=NOW,
            config=DummyEntity(
                id=1,
                restaurant_id=1,
                accept_orders=True,
                preparation_time=15,
                midday_delivery=True,
                evening_delivery=True,
                pickup=True,
                onsite=True,
                reservation=True,
                all_you_can_eat=False,
                a_la_carte=True,
                payment_online=False,
                payment_onsite=True,
                max_delivery_km=5,
            ),
            delivery_tiers=[],
            opening_hours=[],
            is_deleted=False,
        )
    if "user" in text:
        return DummyEntity(
            id=1,
            email="test@example.com",
            first_name="Test",
            last_name="User",
            phone="+33123456789",
            created_at=NOW,
            expo_push_token="ExponentPushToken[test]",
            notify_orders=True,
            notify_reservations=True,
            is_admin=True,
            roles=[DummyEntity(restaurant_id=1, type="owner")],
            hashed_password=hash_password("string"),
        )
    return DummyEntity()


def generic_stub(name: str, is_async: bool):
    async def async_stub(*args: Any, **kwargs: Any) -> Any:
        return generic_value(name)

    def sync_stub(*args: Any, **kwargs: Any) -> Any:
        return generic_value(name)

    return async_stub if is_async else sync_stub


def generic_value(name: str) -> Any:
    lowered = name.lower()
    if lowered in {"get_products", "list_products"}:
        return [sample_for_target("product")]
    if lowered in {"get_product", "create_product", "update_product"}:
        return sample_for_target("product")
    if lowered in {"get_categories", "list_categories"}:
        return [sample_for_target("category")]
    if lowered in {"get_category", "create_category", "update_category"}:
        return sample_for_target("category")
    if lowered in {"get_restaurants_by_user"}:
        return [sample_for_target("restaurant")]
    if lowered in {"get_restaurant", "create_restaurant", "update_restaurant"}:
        return sample_for_target("restaurant")
    if lowered.startswith(("delete_", "unregister_")):
        return None
    if "receipt" in lowered:
        return iter([b"%PDF-1.4 receipt"])
    if "upload_image" in lowered:
        return "https://example.com/image.png"
    if "generate_table_ticket" in lowered:
        return iter([b"%PDF-1.4 test"])
    if "send_hubrise_test_order" in lowered:
        return ({"items": []}, {"status": "ok"})
    if "recommendation" in lowered:
        return {
            "recommendations": [
                {
                    "product_id": 1,
                    "name": "Burger",
                    "price": Decimal("12.50"),
                    "image_url": None,
                    "category_id": 1,
                    "category_name": "Burgers",
                    "score": 0.95,
                    "reason": "Pairs well with current basket",
                    "title": "Recommended add-on",
                    "message": "Popular choice with this order",
                }
            ]
        }
    if "delivery_quote" in lowered:
        return {
            "eligible": True,
            "items_subtotal": 12.5,
            "delivery_fee": 2.5,
            "amount_total": 15.0,
            "distance_km": 1.8,
            "shortfall_amount": 0.0,
            "next_min_order_amount": None,
            "message": "Eligible for delivery",
            "applied_tier": {
                "min_km": 0,
                "max_km": 3,
                "price": 2.5,
                "min_order_amount": 0.0,
            },
        }
    if "connect_status" in lowered:
        return {"restaurant_id": 1, "stripe_account_id": "acct_123", "onboarding_completed": True, "charges_enabled": True, "payouts_enabled": True, "details_submitted": True}
    if "account_link" in lowered or "dashboard_login_link" in lowered:
        return SimpleNamespace(url="https://example.com/stripe", expires_at=int(NOW.timestamp()))
    if "checkout_session" in lowered:
        return SimpleNamespace(id="cs_test_123", url="https://example.com/checkout")
    if "subscription_links" in lowered:
        return {"monthly": "https://example.com/monthly", "yearly": "https://example.com/yearly"}
    if "invoice" in lowered:
        return [{"id": "inv_123", "hosted_invoice_url": "https://example.com/invoice", "status": "paid", "amount_due": 1000, "currency": "eur", "created": int(NOW.timestamp())}]
    if "subscription_usage" in lowered:
        return {
            "plan": "starter",
            "interval": "month",
            "subscription_status": "active",
            "subscription_display_status": "active",
            "subscription_cancel_at_period_end": False,
            "monthly_quota": 100,
            "usage_count": 1,
            "usage_remaining": 99,
            "monthly_token_quota": 10000,
            "token_usage_count": 100,
            "token_usage_remaining": 9900,
            "is_ai_enabled": True,
            "is_quota_reached": False,
            "is_token_quota_reached": False,
        }
    if lowered == "get_order_analytics":
        return {
            "top_items": [
                {
                    "item_name": "Burger",
                    "item_type": "product",
                    "quantity_sold": 10,
                    "revenue": 125.0,
                }
            ],
            "monthly_orders_count": 12,
            "monthly_orders_change": 2,
            "monthly_orders_change_percentage": 20.0,
            "monthly_revenue_change_percentage": 15.0,
            "delivery_percentage": 60.0,
            "pickup_percentage": 40.0,
            "top_delivery_cities": [{"city": "Paris", "orders_count": 8}],
            "best_month": {"label": "January", "orders_count": 20},
            "largest_order": {"amount": 45.5, "created_at": NOW},
            "current_year_orders_count": 120,
            "average_basket": {"amount": 18.5, "change_percentage_vs_previous_year": 5.0},
            "busiest_days": [{"day": "Friday", "orders_count": 30}],
            "busiest_time_slot": {"slot": "19:00-20:00", "orders_count": 18},
            "repeat_purchase": {"rate_percentage": 35.0, "repeat_customers": 14, "identifiable_customers": 40},
        }
    if lowered == "get_revenue_analytics":
        return {
            "current_month_amount": 2500.0,
            "current_month_change_percentage": 12.0,
            "previous_month_amount": 2230.0,
            "yearly_channels": [
                {
                    "year": 2026,
                    "delivery": {"amount": 1500.0, "percentage": 60.0},
                    "pickup": {"amount": 1000.0, "percentage": 40.0},
                }
            ],
            "best_month": {"label": "January", "amount": 2500.0},
            "best_day": {"label": "Friday", "amount": 320.0},
            "yearly_breakdown": [
                {
                    "year": 2026,
                    "total_amount": 2500.0,
                    "months": [{"month": "January", "amount": 2500.0, "annual_percentage": 100.0}],
                }
            ],
            "annual_growth_percentage": 10.0,
            "average_basket": {"amount": 18.5, "change_percentage_vs_previous_month": 3.0},
        }
    if lowered == "get_customer_analytics":
        return {
            "total_customers": {"total": 100, "change_percentage_vs_previous_month": 8.0},
            "loyal_customers": {"total": 25, "percentage_of_total_customers": 25.0},
            "top_customers": [
                {
                    "identity": "jane@example.com",
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "orders_count": 8,
                    "total_spent": 180.0,
                    "last_order_at": NOW,
                }
            ],
            "new_customers_breakdown": [
                {
                    "year": 2026,
                    "months": [{"month": "January", "count": 12, "change_percentage_vs_previous_month": 5.0}],
                }
            ],
        }
    if lowered == "get_restaurant_performance_analytics" or lowered == "get_performance_analytics":
        return {
            "preparation_time": {
                "average_minutes": 18.0,
                "difference_vs_previous_month_minutes": -2.0,
            },
            "preparers": [
                {
                    "user_id": 1,
                    "first_name": "Test",
                    "prepared_orders_count": 10,
                    "average_preparation_minutes": 17.5,
                }
            ],
        }
    if "apply_hubrise_order_update" in lowered:
        return None
    if "verify_hubrise_signature" in lowered:
        return False
    if "list_ai_conversations" in lowered:
        return ([DummyEntity()], 1)
    if "generate_restaurant_ai_response" in lowered:
        return {
            "conversation_id": 1,
            "answer": "Sample AI answer",
            "model": "claude-sonnet-4-6",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
                "remaining_messages": 99,
                "remaining_tokens": 9970,
            },
        }
    if lowered.startswith(("list_", "get_")) and any(token in lowered for token in ["restaurants", "products", "categories", "menus", "customers", "reservations", "users", "offers", "conversations", "messages", "invoices"]):
        return [DummyEntity()]
    if lowered.startswith(("get_", "create_", "update_", "register_", "build_")):
        return DummyEntity()
    return DummyEntity()


def override_current_user() -> DummyEntity:
    return sample_for_target("user")


def override_get_db() -> Iterator[DummySession]:
    yield DummySession()


@pytest.fixture(autouse=True)
def app_test_overrides(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Ne pas appliquer les mocks aux tests d'intégration (ils utilisent une vraie DB)
    if "integration" in str(request.fspath):
        yield
        return

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_get_db

    for module_name, module in sys.modules.items():
        if not module_name.startswith("app.routes."):
            continue
        for attr_name, attr_value in vars(module).items():
            if inspect.isfunction(attr_value) and (
                attr_value.__module__.startswith("app.services.")
                or attr_value.__module__ == "app.core.security"
            ):
                if attr_name == "get_current_user":
                    continue
                monkeypatch.setattr(module, attr_name, generic_stub(attr_name, inspect.iscoroutinefunction(attr_value)))

    yield
    app.dependency_overrides.clear()
