import stripe
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.restaurant import Restaurant
from app.services.subscription_service import apply_subscription_plan


def _require_stripe_secret_key() -> str:
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured on the server",
        )
    return settings.STRIPE_SECRET_KEY


def _configure_stripe() -> None:
    stripe.api_key = _require_stripe_secret_key()


def _main_plan_prices() -> dict[tuple[str, str], str | None]:
    return {
        ("starter", "month"): settings.STRIPE_PRICE_STARTER_MONTHLY,
        ("starter", "year"): settings.STRIPE_PRICE_STARTER_YEARLY,
        ("pro_ai", "month"): settings.STRIPE_PRICE_PRO_AI_MONTHLY,
        ("pro_ai", "year"): settings.STRIPE_PRICE_PRO_AI_YEARLY,
        ("business_ai", "month"): settings.STRIPE_PRICE_BUSINESS_AI_MONTHLY,
        ("business_ai", "year"): settings.STRIPE_PRICE_BUSINESS_AI_YEARLY,
    }


def _addon_prices() -> dict[tuple[str, str], str | None]:
    return {
        ("tablet_rental", "month"): settings.STRIPE_PRICE_TABLET_RENTAL_MONTHLY,
        ("tablet_rental", "year"): settings.STRIPE_PRICE_TABLET_RENTAL_YEARLY,
        ("printer_rental", "month"): settings.STRIPE_PRICE_PRINTER_RENTAL_MONTHLY,
        ("printer_rental", "year"): settings.STRIPE_PRICE_PRINTER_RENTAL_YEARLY,
    }


def _all_price_map() -> dict[str, dict[str, str]]:
    price_map: dict[str, dict[str, str]] = {}
    for (plan, interval), price_id in _main_plan_prices().items():
        if price_id:
            price_map[price_id] = {"kind": "plan", "code": plan, "interval": interval}
    for (addon, interval), price_id in _addon_prices().items():
        if price_id:
            price_map[price_id] = {"kind": "addon", "code": addon, "interval": interval}
    return price_map


def _require_price_id(price_id: str | None, label: str) -> str:
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stripe price is not configured for {label}",
        )
    return price_id


def _build_line_items(subscription_plan: str, subscription_interval: str, has_tablet_rental: bool, has_printer_rental: bool) -> list[dict]:
    line_items = [
        {
            "price": _require_price_id(
                _main_plan_prices().get((subscription_plan, subscription_interval)),
                f"{subscription_plan}_{subscription_interval}",
            ),
            "quantity": 1,
        }
    ]
    if has_tablet_rental:
        line_items.append(
            {
                "price": _require_price_id(
                    _addon_prices().get(("tablet_rental", subscription_interval)),
                    f"tablet_rental_{subscription_interval}",
                ),
                "quantity": 1,
            }
        )
    if has_printer_rental:
        line_items.append(
            {
                "price": _require_price_id(
                    _addon_prices().get(("printer_rental", subscription_interval)),
                    f"printer_rental_{subscription_interval}",
                ),
                "quantity": 1,
            }
        )
    return line_items


def ensure_stripe_customer(db: Session, restaurant: Restaurant) -> Restaurant:
    if restaurant.stripe_customer_id:
        return restaurant
    _configure_stripe()
    customer = stripe.Customer.create(
        email=restaurant.email,
        name=restaurant.name,
        phone=restaurant.phone,
        metadata={"restaurant_id": str(restaurant.id)},
    )
    restaurant.stripe_customer_id = customer.id
    db.commit()
    db.refresh(restaurant)
    return restaurant


def create_subscription_checkout_session(
    db: Session,
    restaurant: Restaurant,
    subscription_plan: str,
    subscription_interval: str,
    has_tablet_rental: bool,
    has_printer_rental: bool,
    success_url: str,
    cancel_url: str,
):
    restaurant = ensure_stripe_customer(db, restaurant)
    if restaurant.stripe_subscription_id and restaurant.subscription_status in {"trialing", "active", "past_due", "unpaid"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restaurant already has an active Stripe subscription. Update it instead of creating a new checkout session.",
        )
    _configure_stripe()
    return stripe.checkout.Session.create(
        mode="subscription",
        customer=restaurant.stripe_customer_id,
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=_build_line_items(subscription_plan, subscription_interval, has_tablet_rental, has_printer_rental),
        allow_promotion_codes=True,
        metadata={
            "restaurant_id": str(restaurant.id),
        },
        subscription_data={
            "metadata": {
                "restaurant_id": str(restaurant.id),
            }
        },
    )


def create_customer_portal_session(db: Session, restaurant: Restaurant, return_url: str):
    restaurant = ensure_stripe_customer(db, restaurant)
    _configure_stripe()
    return stripe.billing_portal.Session.create(customer=restaurant.stripe_customer_id, return_url=return_url)


def _find_existing_subscription_id(db: Session, restaurant: Restaurant) -> tuple[str, str]:
    restaurant = ensure_stripe_customer(db, restaurant)

    if restaurant.stripe_subscription_id:
        return restaurant.stripe_subscription_id, restaurant.stripe_customer_id

    _configure_stripe()
    subscriptions = stripe.Subscription.list(customer=restaurant.stripe_customer_id, status="all", limit=10)
    preferred_statuses = {"trialing", "active", "past_due", "unpaid", "incomplete"}

    for subscription in subscriptions["data"]:
        if subscription.get("status") in preferred_statuses:
            return subscription["id"], restaurant.stripe_customer_id

    if subscriptions["data"]:
        return subscriptions["data"][0]["id"], restaurant.stripe_customer_id

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Restaurant does not have an existing Stripe subscription",
    )


def sync_restaurant_subscription(db: Session, restaurant: Restaurant) -> Restaurant:
    stripe_subscription_id, stripe_customer_id = _find_existing_subscription_id(db, restaurant)
    return sync_restaurant_subscription_from_stripe(db, restaurant, stripe_subscription_id, stripe_customer_id)


def update_restaurant_subscription_in_stripe(
    db: Session,
    restaurant: Restaurant,
    subscription_plan: str,
    subscription_interval: str,
    has_tablet_rental: bool,
    has_printer_rental: bool,
) -> Restaurant:
    stripe_subscription_id, stripe_customer_id = _find_existing_subscription_id(db, restaurant)

    _configure_stripe()
    subscription = stripe.Subscription.retrieve(
        stripe_subscription_id,
        expand=["items.data.price"],
    )

    items: list[dict] = []
    for item in subscription["items"]["data"]:
        items.append({"id": item["id"], "deleted": True})

    for line_item in _build_line_items(subscription_plan, subscription_interval, has_tablet_rental, has_printer_rental):
        items.append({"price": line_item["price"], "quantity": line_item["quantity"]})

    stripe.Subscription.modify(
        stripe_subscription_id,
        items=items,
        proration_behavior="create_prorations",
        metadata={"restaurant_id": str(restaurant.id)},
    )

    return sync_restaurant_subscription_from_stripe(db, restaurant, stripe_subscription_id, stripe_customer_id)


def cancel_restaurant_subscription_in_stripe(db: Session, restaurant: Restaurant, at_period_end: bool = True) -> Restaurant:
    stripe_subscription_id, stripe_customer_id = _find_existing_subscription_id(db, restaurant)

    _configure_stripe()
    if at_period_end:
        stripe.Subscription.modify(stripe_subscription_id, cancel_at_period_end=True)
        return sync_restaurant_subscription_from_stripe(db, restaurant, stripe_subscription_id, stripe_customer_id)

    stripe.Subscription.cancel(stripe_subscription_id)
    return cancel_restaurant_subscription(db, restaurant)


def list_restaurant_invoices(db: Session, restaurant: Restaurant) -> list[dict]:
    restaurant = ensure_stripe_customer(db, restaurant)
    _configure_stripe()
    invoices = stripe.Invoice.list(customer=restaurant.stripe_customer_id, limit=24)
    return [
        {
            "id": invoice["id"],
            "status": invoice.get("status"),
            "currency": invoice.get("currency"),
            "total": invoice.get("total"),
            "hosted_invoice_url": invoice.get("hosted_invoice_url"),
            "invoice_pdf": invoice.get("invoice_pdf"),
            "created": invoice.get("created"),
        }
        for invoice in invoices["data"]
    ]


def sync_restaurant_subscription_from_stripe(
    db: Session,
    restaurant: Restaurant,
    stripe_subscription_id: str,
    stripe_customer_id: str | None = None,
) -> Restaurant:
    _configure_stripe()
    subscription = stripe.Subscription.retrieve(stripe_subscription_id, expand=["items.data.price"])

    price_map = _all_price_map()
    subscription_plan: str | None = None
    subscription_interval: str | None = None
    has_tablet_rental = False
    has_printer_rental = False

    for item in subscription["items"]["data"]:
        mapping = price_map.get(item["price"]["id"])
        if not mapping:
            continue
        if mapping["kind"] == "plan":
            subscription_plan = mapping["code"]
            subscription_interval = mapping["interval"]
        elif mapping["code"] == "tablet_rental":
            has_tablet_rental = True
        elif mapping["code"] == "printer_rental":
            has_printer_rental = True

    if not subscription_plan or not subscription_interval:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to map Stripe subscription prices to Yumco plans",
        )

    restaurant.stripe_customer_id = stripe_customer_id or subscription.get("customer")
    restaurant.stripe_subscription_id = subscription.id
    restaurant.subscription_status = subscription.status
    restaurant.subscription_interval = subscription_interval
    restaurant.has_tablet_rental = has_tablet_rental
    restaurant.has_printer_rental = has_printer_rental
    db.commit()
    db.refresh(restaurant)

    restaurant = apply_subscription_plan(db, restaurant, subscription_plan)
    restaurant.subscription_interval = subscription_interval
    restaurant.subscription_status = subscription.status
    restaurant.stripe_customer_id = stripe_customer_id or subscription.get("customer")
    restaurant.stripe_subscription_id = subscription.id
    restaurant.has_tablet_rental = has_tablet_rental
    restaurant.has_printer_rental = has_printer_rental
    db.commit()
    db.refresh(restaurant)
    return restaurant


def cancel_restaurant_subscription(db: Session, restaurant: Restaurant) -> Restaurant:
    restaurant.subscription_status = "canceled"
    restaurant.stripe_subscription_id = None
    restaurant.subscription_interval = "month"
    restaurant.has_tablet_rental = False
    restaurant.has_printer_rental = False
    db.commit()
    db.refresh(restaurant)
    return apply_subscription_plan(db, restaurant, "starter")
