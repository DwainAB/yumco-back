from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.restaurant_promo_code import RestaurantPromoCode


MONEY_QUANT = Decimal("0.01")


def _money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def get_promo_code_by_id(db: Session, restaurant_id: int, promo_code_id: int) -> RestaurantPromoCode | None:
    return (
        db.query(RestaurantPromoCode)
        .filter(
            RestaurantPromoCode.id == promo_code_id,
            RestaurantPromoCode.restaurant_id == restaurant_id,
        )
        .first()
    )


def list_promo_codes(db: Session, restaurant_id: int) -> list[RestaurantPromoCode]:
    return (
        db.query(RestaurantPromoCode)
        .filter(RestaurantPromoCode.restaurant_id == restaurant_id)
        .order_by(RestaurantPromoCode.created_at.desc())
        .all()
    )


def get_promo_code_by_code(db: Session, restaurant_id: int, code: str) -> RestaurantPromoCode | None:
    normalized_code = code.strip().upper()
    return (
        db.query(RestaurantPromoCode)
        .filter(
            RestaurantPromoCode.restaurant_id == restaurant_id,
            RestaurantPromoCode.code == normalized_code,
        )
        .first()
    )


def ensure_unique_promo_code(
    db: Session,
    restaurant_id: int,
    code: str,
    exclude_promo_code_id: int | None = None,
) -> None:
    query = db.query(RestaurantPromoCode).filter(
        RestaurantPromoCode.restaurant_id == restaurant_id,
        RestaurantPromoCode.code == code.strip().upper(),
    )
    if exclude_promo_code_id is not None:
        query = query.filter(RestaurantPromoCode.id != exclude_promo_code_id)

    existing = query.first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un code promo avec ce code existe deja pour ce restaurant",
        )


def validate_promo_code_for_order(
    db: Session,
    restaurant_id: int,
    code: str,
    items_subtotal: Decimal,
) -> tuple[RestaurantPromoCode, Decimal]:
    promo_code = get_promo_code_by_code(db, restaurant_id, code)
    if not promo_code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code promo introuvable")

    now = datetime.now(timezone.utc)
    if not promo_code.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ce code promo est désactivé")
    if promo_code.start_at and promo_code.start_at > now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ce code promo n'est pas encore actif")
    if promo_code.end_at and promo_code.end_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ce code promo a expiré")
    if promo_code.usage_limit is not None and int(promo_code.usage_count or 0) >= int(promo_code.usage_limit):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ce code promo a atteint sa limite d'utilisation")

    subtotal = _money(items_subtotal)
    if subtotal <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Le panier doit être supérieur à 0")
    minimum_order_amount = _money(promo_code.minimum_order_amount or 0)
    if subtotal < minimum_order_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ce code promo est valable à partir de {float(minimum_order_amount):.2f} EUR de commande",
        )

    discount_value = _money(promo_code.discount_value)
    if promo_code.discount_type == "percent":
        discount_amount = (subtotal * discount_value / Decimal("100")).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    else:
        discount_amount = discount_value

    discount_amount = min(subtotal, _money(discount_amount))
    return promo_code, discount_amount


def increment_promo_code_usage(db: Session, restaurant_id: int, code: str) -> None:
    promo_code = get_promo_code_by_code(db, restaurant_id, code)
    if not promo_code:
        return
    promo_code.usage_count = int(promo_code.usage_count or 0) + 1
