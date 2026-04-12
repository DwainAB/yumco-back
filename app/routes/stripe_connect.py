import stripe
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.db.database import get_db
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.restaurant_config import RestaurantConfig
from app.models.role import Role
from app.models.user import User
from app.schemas.stripe_connect import (
    StripeCheckoutSessionRequest,
    StripeCheckoutSessionResponse,
    StripeConnectAccountResponse,
    StripeDraftCheckoutSessionRequest,
    StripeConnectLinkRequest,
    StripeConnectLinkResponse,
)
from app.services.stripe_connect_service import (
    build_connect_status,
    create_account_link,
    create_connected_account,
    create_draft_order_checkout_session,
    create_dashboard_login_link,
    create_order_checkout_session,
    refresh_connected_account,
    sync_order_payment_from_charge,
    sync_order_payment_from_checkout,
)


router = APIRouter(tags=["stripe-connect"])


def _require_restaurant_owner_or_admin(restaurant_id: int, current_user: User, db: Session) -> Restaurant:
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id, Restaurant.is_deleted.is_(False)).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    if current_user.is_admin:
        return restaurant

    role = db.query(Role).filter(Role.restaurant_id == restaurant_id, Role.user_id == current_user.id).first()
    if not role or role.type not in {"owner", "manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return restaurant


@router.get("/restaurants/{restaurant_id}/stripe/connect", response_model=StripeConnectAccountResponse)
def get_connect_status(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    if restaurant.stripe_id:
        restaurant = refresh_connected_account(db, restaurant)
    return build_connect_status(restaurant)


@router.post("/restaurants/{restaurant_id}/stripe/connect/account", response_model=StripeConnectAccountResponse)
def ensure_connect_account(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    restaurant = create_connected_account(db, restaurant)
    return build_connect_status(restaurant)


@router.post("/restaurants/{restaurant_id}/stripe/connect/onboarding", response_model=StripeConnectLinkResponse)
def create_connect_onboarding_link(
    restaurant_id: int,
    data: StripeConnectLinkRequest = Body(default_factory=StripeConnectLinkRequest),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    link = create_account_link(
        db,
        restaurant,
        return_url=str(data.return_url) if data.return_url else None,
        refresh_url=str(data.refresh_url) if data.refresh_url else None,
    )
    return {"url": link.url, "expires_at": getattr(link, "expires_at", None)}


@router.post("/restaurants/{restaurant_id}/stripe/connect/dashboard", response_model=StripeConnectLinkResponse)
def create_express_dashboard_link(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    link = create_dashboard_login_link(db, restaurant)
    return {"url": link.url, "expires_at": None}


@router.post("/restaurants/{restaurant_id}/orders/{order_id}/checkout-session", response_model=StripeCheckoutSessionResponse)
def create_order_checkout(
    restaurant_id: int,
    order_id: int,
    data: StripeCheckoutSessionRequest,
    db: Session = Depends(get_db),
):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id, Restaurant.is_deleted.is_(False)).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    session = create_order_checkout_session(db, restaurant, order, str(data.success_url), str(data.cancel_url))
    return {"checkout_session_id": session.id, "checkout_url": session.url}


@router.post("/restaurants/{restaurant_id}/orders/checkout-session", response_model=StripeCheckoutSessionResponse)
def create_draft_order_checkout(
    restaurant_id: int,
    data: StripeDraftCheckoutSessionRequest,
    db: Session = Depends(get_db),
):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id, Restaurant.is_deleted.is_(False)).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    restaurant_config = db.query(RestaurantConfig).filter(RestaurantConfig.restaurant_id == restaurant_id).first()
    if not restaurant_config or not restaurant_config.payment_online:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Online payment is not enabled for this restaurant")

    session = create_draft_order_checkout_session(db, restaurant, data.order, str(data.success_url), str(data.cancel_url))
    return {"checkout_session_id": session.id, "checkout_url": session.url}


@router.post("/stripe/webhooks", status_code=status.HTTP_200_OK)
async def handle_stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    payload = await request.body()
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload=payload, sig_header=stripe_signature, secret=webhook_secret)
        else:
            event = stripe.Event.construct_from(await request.json(), stripe.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe payload") from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature") from exc

    event_type = event["type"]
    event_object = event["data"]["object"]
    print("[stripe_webhook] received event", {"type": event_type, "account": event.get("account")})

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        sync_order_payment_from_checkout(db, event_object)
    elif event_type == "checkout.session.async_payment_failed":
        print("[stripe_webhook] async payment failed", {"session_id": event_object.get("id")})
    elif event_type in {"charge.succeeded", "charge.refunded"}:
        sync_order_payment_from_charge(db, event_object)

    return Response(status_code=status.HTTP_200_OK)
