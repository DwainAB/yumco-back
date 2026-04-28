from __future__ import annotations

import os
import pytest
from collections.abc import Generator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.test", override=True)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.core.security import hash_password, create_access_token
from main import app


TEST_DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _bootstrap_test_db():
    """Recrée toutes les tables à partir des modèles SQLAlchemy."""
    # Import de tous les modèles pour que Base.metadata les connaisse
    import app.models.user  # noqa
    import app.models.restaurant  # noqa
    import app.models.restaurant_config  # noqa
    import app.models.role  # noqa
    import app.models.address  # noqa
    import app.models.category  # noqa
    import app.models.product  # noqa
    import app.models.menu  # noqa
    import app.models.menu_category  # noqa
    import app.models.menu_option  # noqa
    import app.models.all_you_can_eat  # noqa
    import app.models.table  # noqa
    import app.models.reservation  # noqa
    import app.models.order  # noqa
    import app.models.order_item  # noqa
    import app.models.opening_hours  # noqa
    import app.models.customer  # noqa
    import app.models.delivery_tiers  # noqa
    import app.models.hubrise_connection  # noqa
    import app.models.hubrise_order_log  # noqa
    import app.models.ai_conversation  # noqa
    import app.models.ai_conversation_message  # noqa
    import app.models.user_device  # noqa
    import app.models.pending_online_order  # noqa

    from app.db.database import Base

    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    Base.metadata.create_all(bind=engine)


_bootstrap_test_db()

# Tables à vider entre chaque test (ordre respectant les FK)
TRUNCATE_ORDER = [
    "ai_conversation_messages",
    "ai_conversations",
    "hubrise_order_logs",
    "hubrise_connections",
    "order_items",
    "orders",
    "delivery_tiers",
    "all_you_can_eat",
    "menu_options",
    "menu_categories",
    "menus",
    "products",
    "categories",
    "opening_hours",
    "reservations",
    "tables",
    "restaurant_configs",
    "user_devices",
    "roles",
    "restaurants",
    "addresses",
    "users",
]


def run_migrations():
    from alembic.config import Config
    from alembic import command
    alembic_cfg = Config(str(ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")


def drop_schema():
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()


def truncate_all():
    with engine.connect() as conn:
        for table in TRUNCATE_ORDER:
            try:
                conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
            except Exception:
                pass
        conn.commit()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_db():
    """Vide toutes les tables avant chaque test."""
    truncate_all()
    yield


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db: Session) -> TestClient:
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_user(
    db: Session,
    email: str = "owner@test.com",
    password: str = "password123",
    is_admin: bool = False,
):
    from app.models.user import User
    user = User(
        email=email,
        first_name="Test",
        last_name="Owner",
        phone="+33600000001",
        hashed_password=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_restaurant(db: Session, owner_id: int, name: str = "Test Restaurant"):
    from app.models.restaurant import Restaurant
    from app.models.restaurant_config import RestaurantConfig
    from app.models.role import Role
    from app.models.address import Address

    address = Address(street="1 Rue du Test", city="Paris", postal_code="75001", country="FR")
    db.add(address)
    db.flush()

    restaurant = Restaurant(
        name=name,
        email="contact@test.com",
        phone="+33100000001",
        timezone="Europe/Paris",
        address_id=address.id,
        subscription_status="active",
        subscription_plan="starter",
        ai_monthly_quota=100,
        ai_monthly_token_quota=10000,
    )
    db.add(restaurant)
    db.flush()

    db.add(RestaurantConfig(
        restaurant_id=restaurant.id,
        accept_orders=True,
        preparation_time=15,
        pickup=True,
        onsite=True,
        payment_onsite=True,
    ))
    db.add(Role(user_id=owner_id, restaurant_id=restaurant.id, type="owner"))
    db.commit()
    db.refresh(restaurant)
    return restaurant


def make_category(db: Session, restaurant_id: int, name: str = "Burgers"):
    from app.models.category import Category
    cat = Category(restaurant_id=restaurant_id, name=name)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def make_product(db: Session, restaurant_id: int, category_id: int, name: str = "Burger", price: float = 12.5):
    from app.models.product import Product
    from decimal import Decimal
    product = Product(
        restaurant_id=restaurant_id,
        category_id=category_id,
        name=name,
        price=Decimal(str(price)),
        is_available=True,
        available_online=True,
        available_onsite=True,
        group="main",
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def auth_headers(email: str) -> dict:
    token = create_access_token({"sub": email})
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, email: str, password: str) -> dict:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed: {res.text}"
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
