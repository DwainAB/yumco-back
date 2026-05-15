import json
from decimal import Decimal, ROUND_HALF_UP

import stripe
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.order import Order
from app.models.pending_online_order import PendingOnlineOrder
from app.models.restaurant import Restaurant
from app.schemas.order import OrderCreate
from app.services.order_service import calculate_order_pricing, compute_items_subtotal, create_order


def _require_stripe_secret_key() -> str:
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured on the server",
        )
    return settings.STRIPE_SECRET_KEY


def _configure_stripe() -> None:
    stripe.api_key = _require_stripe_secret_key()


def _amount_to_cents(amount: Decimal | float | int) -> int:
    decimal_amount = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    return int((decimal_amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _build_default_url(path: str) -> str:
    base_url = settings.FRONTEND_BASE_URL or settings.APP_BASE_URL
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A return URL must be provided or FRONTEND_BASE_URL/APP_BASE_URL must be configured",
        )
    return f"{base_url.rstrip('/')}{path}"


def create_connected_account(db: Session, restaurant: Restaurant) -> Restaurant:
    if restaurant.stripe_id:
        return refresh_connected_account(db, restaurant)

    _configure_stripe()
    account = stripe.Account.create(
        type="express",
        country="FR",
        email=restaurant.email,
        business_type="company",
        capabilities={
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
        metadata={
            "restaurant_id": str(restaurant.id),
            "restaurant_name": restaurant.name,
        },
    )

    restaurant.stripe_id = account.id
    restaurant.stripe_charges_enabled = bool(account.charges_enabled)
    restaurant.stripe_payouts_enabled = bool(account.payouts_enabled)
    restaurant.stripe_details_submitted = bool(account.details_submitted)
    db.commit()
    db.refresh(restaurant)
    return restaurant


def refresh_connected_account(db: Session, restaurant: Restaurant) -> Restaurant:
    if not restaurant.stripe_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stripe account not found for this restaurant")

    _configure_stripe()
    account = stripe.Account.retrieve(restaurant.stripe_id)
    restaurant.stripe_charges_enabled = bool(account.charges_enabled)
    restaurant.stripe_payouts_enabled = bool(account.payouts_enabled)
    restaurant.stripe_details_submitted = bool(account.details_submitted)
    db.commit()
    db.refresh(restaurant)
    return restaurant


def create_account_link(db: Session, restaurant: Restaurant, return_url: str | None = None, refresh_url: str | None = None):
    restaurant = create_connected_account(db, restaurant)
    _configure_stripe()
    return stripe.AccountLink.create(
        account=restaurant.stripe_id,
        refresh_url=refresh_url or _build_default_url(f"/restaurants/{restaurant.id}/stripe/refresh"),
        return_url=return_url or _build_default_url(f"/restaurants/{restaurant.id}/stripe/return"),
        type="account_onboarding",
    )


def create_dashboard_login_link(db: Session, restaurant: Restaurant):
    restaurant = refresh_connected_account(db, restaurant)
    if not restaurant.stripe_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stripe account not found for this restaurant")

    _configure_stripe()
    return stripe.Account.create_login_link(restaurant.stripe_id)


def create_draft_order_checkout_session(db: Session, restaurant: Restaurant, order_data: OrderCreate, success_url: str, cancel_url: str):
    restaurant = refresh_connected_account(db, restaurant)
    if not restaurant.stripe_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Restaurant is not connected to Stripe")
    if not restaurant.stripe_charges_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Restaurant Stripe account is not ready to accept payments")

    _configure_stripe()
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=[
            {
                "quantity": 1,
                "price_data": {
                    "currency": "eur",
                    "unit_amount": _amount_to_cents(_compute_order_total(db, restaurant, order_data)),
                    "product_data": {
                        "name": f"Commande {restaurant.name}",
                        "description": f"Commande Yumco pour {restaurant.name}",
                    },
                },
            }
        ],
        metadata={
            "restaurant_id": str(restaurant.id),
            "flow": "draft_order",
        },
        payment_intent_data={
            "metadata": {
                "restaurant_id": str(restaurant.id),
                "flow": "draft_order",
            }
        },
        stripe_account=restaurant.stripe_id,
    )

    pending_order = PendingOnlineOrder(
        restaurant_id=restaurant.id,
        checkout_session_id=session.id,
        payload_json=order_data.model_dump_json(),
    )
    db.add(pending_order)
    db.commit()
    return session


def build_connect_status(restaurant: Restaurant) -> dict:
    return {
        "restaurant_id": restaurant.id,
        "stripe_account_id": restaurant.stripe_id,
        "onboarding_completed": bool(restaurant.stripe_details_submitted and restaurant.stripe_charges_enabled and restaurant.stripe_payouts_enabled),
        "charges_enabled": bool(restaurant.stripe_charges_enabled),
        "payouts_enabled": bool(restaurant.stripe_payouts_enabled),
        "details_submitted": bool(restaurant.stripe_details_submitted),
    }


def sync_order_payment_from_checkout(db: Session, session_payload: stripe.checkout.Session) -> None:
    metadata = session_payload.get("metadata") or {}
    order_id = metadata.get("order_id")
    print(
        "[stripe_connect] checkout event received",
        {
            "session_id": session_payload.get("id"),
            "order_id": order_id,
            "metadata": metadata,
        },
    )
    if not order_id:
        checkout_session_id = session_payload.get("id")
        if not checkout_session_id:
            print("[stripe_connect] checkout event skipped: missing session id")
            return None
        pending_order = (
            db.query(PendingOnlineOrder)
            .filter(PendingOnlineOrder.checkout_session_id == checkout_session_id)
            .first()
        )
        if not pending_order:
            print("[stripe_connect] checkout event skipped: pending order not found", {"session_id": checkout_session_id})
            return None

        order_data = OrderCreate(**json.loads(pending_order.payload_json))
        order = create_order(db, pending_order.restaurant_id, order_data)
        order.payment_status = "paid"
        order.stripe_checkout_session_id = session_payload.get("id")
        order.stripe_payment_intent_id = session_payload.get("payment_intent")
        db.delete(pending_order)
        db.commit()
        print("[stripe_connect] order created from pending checkout", {"order_id": order.id, "session_id": checkout_session_id})
        return order

    order = db.query(Order).filter(Order.id == int(order_id)).first()
    if not order:
        print("[stripe_connect] checkout event skipped: order not found", {"order_id": order_id})
        return None

    order.stripe_checkout_session_id = session_payload.get("id")
    order.stripe_payment_intent_id = session_payload.get("payment_intent")
    order.payment_status = "paid"
    db.commit()
    print("[stripe_connect] existing order marked as paid", {"order_id": order.id})
    return order


def sync_order_payment_from_charge(db: Session, charge_payload: stripe.Charge) -> None:
    metadata = charge_payload.get("metadata") or {}
    order_id = metadata.get("order_id")
    if not order_id:
        return

    order = db.query(Order).filter(Order.id == int(order_id)).first()
    if not order:
        return

    order.stripe_charge_id = charge_payload.get("id")
    order.stripe_payment_intent_id = charge_payload.get("payment_intent")
    order.payment_status = "refunded" if charge_payload.get("refunded") else "paid"
    db.commit()


def _compute_order_total(db: Session, restaurant: Restaurant, data: OrderCreate) -> Decimal:
    items_subtotal = compute_items_subtotal(db, data.items)
    address = None
    if data.type == "delivery" and data.address:
        from app.models.address import Address

        address = Address(**data.address.model_dump())

    pricing = calculate_order_pricing(
        db=db,
        restaurant=restaurant,
        order_type=data.type,
        items_subtotal=items_subtotal,
        address_data=address,
        promo_code=data.promo_code,
    )
    return pricing["amount_total"]
