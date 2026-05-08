from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.schemas.address import AddressCreate
from app.schemas.order import OrderItemCreate


ALLOWED_DISCOUNT_TYPES = {"percent", "fixed"}


def _normalize_discount_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_DISCOUNT_TYPES:
        raise ValueError("discount_type must be 'percent' or 'fixed'")
    return normalized


class PromoCodeBase(BaseModel):
    code: str
    discount_type: str
    discount_value: Decimal
    start_at: datetime | None = None
    end_at: datetime | None = None
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("code is required")
        return normalized

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(cls, value: str) -> str:
        return _normalize_discount_type(value)

    @field_validator("discount_value")
    @classmethod
    def validate_discount_value(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("discount_value must be greater than 0")
        return value

    @field_validator("end_at")
    @classmethod
    def validate_dates(cls, value: datetime | None, info) -> datetime | None:
        start_at = info.data.get("start_at")
        if value and start_at and value <= start_at:
            raise ValueError("end_at must be after start_at")
        return value


class PromoCodeCreate(PromoCodeBase):
    pass


class PromoCodeUpdate(BaseModel):
    code: str | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("code is required")
        return normalized

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_discount_type(value)

    @field_validator("discount_value")
    @classmethod
    def validate_discount_value(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if value <= 0:
            raise ValueError("discount_value must be greater than 0")
        return value


class PromoCodeResponse(PromoCodeBase):
    id: int
    restaurant_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class PromoCodeValidationRequest(BaseModel):
    promo_code: str
    type: str
    items: list[OrderItemCreate]
    address: AddressCreate | None = None

    @field_validator("promo_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("promo_code is required")
        return normalized


class PromoCodeValidationResponse(BaseModel):
    promo_code: str
    discount_type: str
    discount_value: float
    items_subtotal: float
    discount_amount: float
    discounted_subtotal: float
    delivery_fee: float
    amount_total: float
