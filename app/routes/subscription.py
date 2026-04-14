from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.restaurant import Restaurant
from app.models.role import Role
from app.models.user import User
from app.schemas.restaurant import RestaurantResponse, RestaurantSubscriptionUsage
from app.schemas.stripe_billing import (
    StripeAdminSubscriptionLinksResponse,
    StripeInvoiceResponse,
    StripeSubscriptionCheckoutRequest,
    StripeSubscriptionCheckoutResponse,
    StripeSubscriptionUpdateRequest,
)
from app.services.stripe_billing_service import (
    cancel_restaurant_subscription_in_stripe,
    create_subscription_checkout_session,
    get_admin_subscription_links,
    list_restaurant_invoices,
    sync_restaurant_subscription,
    update_restaurant_subscription_in_stripe,
)
from app.services.subscription_service import get_subscription_usage


router = APIRouter(prefix="/restaurants", tags=["subscriptions"])


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


@router.get("/{restaurant_id}/subscription", response_model=RestaurantSubscriptionUsage)
def get_restaurant_subscription(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return get_subscription_usage(db, restaurant)


@router.post("/{restaurant_id}/subscription/checkout-session", response_model=StripeSubscriptionCheckoutResponse)
def create_subscription_checkout(
    restaurant_id: int,
    data: StripeSubscriptionCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    session = create_subscription_checkout_session(
        db,
        restaurant,
        data.subscription_plan,
        data.subscription_interval,
        data.has_tablet_rental,
        data.has_printer_rental,
        str(data.success_url),
        str(data.cancel_url),
    )
    return {"checkout_session_id": session.id, "checkout_url": session.url}


@router.put("/{restaurant_id}/subscription/stripe", response_model=RestaurantResponse)
def update_subscription_in_stripe(
    restaurant_id: int,
    data: StripeSubscriptionUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return update_restaurant_subscription_in_stripe(
        db,
        restaurant,
        data.subscription_plan,
        data.subscription_interval,
        data.has_tablet_rental,
        data.has_printer_rental,
    )


@router.post("/{restaurant_id}/subscription/stripe/sync", response_model=RestaurantResponse)
def sync_subscription_from_stripe(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return sync_restaurant_subscription(db, restaurant)


@router.delete("/{restaurant_id}/subscription/stripe", response_model=RestaurantResponse)
def cancel_subscription_in_stripe(
    restaurant_id: int,
    at_period_end: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return cancel_restaurant_subscription_in_stripe(db, restaurant, at_period_end=at_period_end)


@router.get("/{restaurant_id}/subscription/stripe-links", response_model=StripeAdminSubscriptionLinksResponse)
def get_subscription_links(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return get_admin_subscription_links(restaurant)


@router.get("/{restaurant_id}/subscription/invoices", response_model=list[StripeInvoiceResponse])
def get_subscription_invoices(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = _require_restaurant_owner_or_admin(restaurant_id, current_user, db)
    return list_restaurant_invoices(db, restaurant)
