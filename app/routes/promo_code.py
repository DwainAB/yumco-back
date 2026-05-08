from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.restaurant_promo_code import RestaurantPromoCode
from app.schemas.promo_code import (
    PromoCodeCreate,
    PromoCodeResponse,
    PromoCodeUpdate,
    PromoCodeValidationRequest,
    PromoCodeValidationResponse,
)
from app.services.order_service import calculate_order_pricing, compute_items_subtotal
from app.services.promo_code_service import (
    get_promo_code_by_id,
    list_promo_codes,
)


router = APIRouter(prefix="/restaurants", tags=["promo-codes"])


def _get_restaurant_or_404(db: Session, restaurant_id: int) -> Restaurant:
    restaurant = (
        db.query(Restaurant)
        .filter(Restaurant.id == restaurant_id, Restaurant.is_deleted.is_(False))
        .first()
    )
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return restaurant


@router.get("/{restaurant_id}/promo-codes", response_model=list[PromoCodeResponse])
def get_restaurant_promo_codes(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_restaurant_or_404(db, restaurant_id)
    return list_promo_codes(db, restaurant_id)


@router.post("/{restaurant_id}/promo-codes", response_model=PromoCodeResponse, status_code=status.HTTP_201_CREATED)
def create_restaurant_promo_code(
    restaurant_id: int,
    data: PromoCodeCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_restaurant_or_404(db, restaurant_id)
    promo_code = RestaurantPromoCode(restaurant_id=restaurant_id, **data.model_dump())
    db.add(promo_code)
    db.commit()
    db.refresh(promo_code)
    return promo_code


@router.put("/{restaurant_id}/promo-codes/{promo_code_id}", response_model=PromoCodeResponse)
def update_restaurant_promo_code(
    restaurant_id: int,
    promo_code_id: int,
    data: PromoCodeUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_restaurant_or_404(db, restaurant_id)
    promo_code = get_promo_code_by_id(db, restaurant_id, promo_code_id)
    if not promo_code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code promo introuvable")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(promo_code, field, value)

    db.commit()
    db.refresh(promo_code)
    return promo_code


@router.delete("/{restaurant_id}/promo-codes/{promo_code_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_restaurant_promo_code(
    restaurant_id: int,
    promo_code_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_restaurant_or_404(db, restaurant_id)
    promo_code = get_promo_code_by_id(db, restaurant_id, promo_code_id)
    if not promo_code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code promo introuvable")
    db.delete(promo_code)
    db.commit()


@router.post("/{restaurant_id}/promo-codes/validate", response_model=PromoCodeValidationResponse)
def validate_restaurant_promo_code(
    restaurant_id: int,
    data: PromoCodeValidationRequest,
    db: Session = Depends(get_db),
):
    restaurant = _get_restaurant_or_404(db, restaurant_id)
    items_subtotal = compute_items_subtotal(db, data.items)
    pricing = calculate_order_pricing(
        db=db,
        restaurant=restaurant,
        order_type=data.type,
        items_subtotal=items_subtotal,
        address_data=data.address,
        promo_code=data.promo_code,
    )
    return PromoCodeValidationResponse(
        promo_code=data.promo_code,
        discount_type=str(pricing["discount_type"]),
        discount_value=float(pricing["discount_value"] or Decimal("0")),
        items_subtotal=float(pricing["items_subtotal"]),
        discount_amount=float(pricing["discount_amount"]),
        discounted_subtotal=float(pricing["discounted_subtotal"]),
        delivery_fee=float(pricing["delivery_fee"]),
        amount_total=float(pricing["amount_total"]),
    )
