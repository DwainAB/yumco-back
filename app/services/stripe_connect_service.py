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
from app.services.order_service import create_order


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


def create_order_checkout_session(db: Session, restaurant: Restaurant, order: Order, success_url: str, cancel_url: str):
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
                    "unit_amount": _amount_to_cents(order.amount_total),
                    "product_data": {
                        "name": f"Commande {order.order_number}",
                        "description": f"Commande Yumco pour {restaurant.name}",
                    },
                },
            }
        ],
        metadata={
            "restaurant_id": str(restaurant.id),
            "order_id": str(order.id),
            "order_number": order.order_number,
        },
        payment_intent_data={
            "metadata": {
                "restaurant_id": str(restaurant.id),
                "order_id": str(order.id),
                "order_number": order.order_number,
            }
        },
        stripe_account=restaurant.stripe_id,
    )

    order.stripe_checkout_session_id = session.id
    order.payment_status = "awaiting_payment"
    db.commit()
    db.refresh(order)
    return session


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
                    "unit_amount": _amount_to_cents(_compute_order_total(db, order_data)),
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
            return
        pending_order = (
            db.query(PendingOnlineOrder)
            .filter(PendingOnlineOrder.checkout_session_id == checkout_session_id)
            .first()
        )
        if not pending_order:
            print("[stripe_connect] checkout event skipped: pending order not found", {"session_id": checkout_session_id})
            return

        order_data = OrderCreate(**json.loads(pending_order.payload_json))
        order = create_order(db, pending_order.restaurant_id, order_data)
        order.payment_status = "paid"
        order.stripe_checkout_session_id = session_payload.get("id")
        order.stripe_payment_intent_id = session_payload.get("payment_intent")
        db.delete(pending_order)
        db.commit()
        print("[stripe_connect] order created from pending checkout", {"order_id": order.id, "session_id": checkout_session_id})
        return

    order = db.query(Order).filter(Order.id == int(order_id)).first()
    if not order:
        print("[stripe_connect] checkout event skipped: order not found", {"order_id": order_id})
        return

    order.stripe_checkout_session_id = session_payload.get("id")
    order.stripe_payment_intent_id = session_payload.get("payment_intent")
    order.payment_status = "paid"
    db.commit()
    print("[stripe_connect] existing order marked as paid", {"order_id": order.id})


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


def _compute_order_total(db: Session, data: OrderCreate) -> Decimal:
    from app.models.all_you_can_eat import AllYouCanEat
    from app.models.menu import Menu
    from app.models.menu_option import MenuOption
    from app.models.product import Product

    amount_total = Decimal("0")

    for item in data.items:
        if item.product_id:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise HTTPException(status_code=400, detail=f"Product {item.product_id} not found")
            amount_total += Decimal(str(product.price)) * item.quantity
        elif item.menu_id:
            menu = db.query(Menu).filter(Menu.id == item.menu_id).first()
            if not menu:
                raise HTTPException(status_code=400, detail=f"Menu {item.menu_id} not found")
            unit_price = Decimal(str(menu.price))
            for option_id in item.selected_options:
                option = db.query(MenuOption).filter(MenuOption.id == option_id).first()
                if not option:
                    raise HTTPException(status_code=400, detail=f"MenuOption {option_id} not found")
                unit_price += Decimal(str(option.additional_price))
            amount_total += unit_price * item.quantity
        elif item.all_you_can_eat_id:
            ayce = db.query(AllYouCanEat).filter(AllYouCanEat.id == item.all_you_can_eat_id).first()
            if not ayce:
                raise HTTPException(status_code=400, detail=f"AllYouCanEat offer {item.all_you_can_eat_id} not found")
            amount_total += Decimal(str(ayce.price)) * item.quantity
        else:
            raise HTTPException(status_code=400, detail="Each item must have a product_id, menu_id, or all_you_can_eat_id")

    return amount_total
