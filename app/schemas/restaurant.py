from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from app.schemas.address import AddressCreate, AddressUpdate, AddressResponse
from app.schemas.restaurant_config import RestaurantConfigResponse, RestaurantConfigUpdate
from app.schemas.delivery_tiers import DeliveryTierCreate, DeliveryTierResponse
from app.schemas.opening_hours import OpeningHoursCreate, OpeningHoursResponse


ALLOWED_SUBSCRIPTION_PLANS = {"starter", "pro_ai", "business_ai"}


def _normalize_subscription_plan(value: str | None) -> str | None:
    if value is None:
        return value
    normalized = value.strip().lower()
    if normalized not in ALLOWED_SUBSCRIPTION_PLANS:
        raise ValueError(f"subscription_plan must be one of: {', '.join(sorted(ALLOWED_SUBSCRIPTION_PLANS))}")
    return normalized

#Data required to create a restaurant
class RestaurantCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str
    address: AddressCreate
    subscription_plan: str = "starter"
    config: RestaurantConfigUpdate | None = None
    delivery_tiers: list[DeliveryTierCreate] | None = None
    opening_hours: list[OpeningHoursCreate] | None = None

    @field_validator("subscription_plan")
    @classmethod
    def validate_subscription_plan(cls, value: str) -> str:
        normalized = _normalize_subscription_plan(value)
        assert normalized is not None
        return normalized

#Data for updating a restaurant
class RestaurantUpdate(BaseModel):
    name: str | None = None
    email : EmailStr | None = None
    phone : str | None = None
    stripe_id: str | None = None
    timezone: str | None = None
    subscription_plan: str | None = None
    ai_monthly_quota: int | None = None
    ai_usage_count: int | None = None
    ai_monthly_token_quota: int | None = None
    ai_token_usage_count: int | None = None
    ai_cycle_started_at: datetime | None = None
    address: AddressUpdate | None = None
    config: RestaurantConfigUpdate | None = None
    delivery_tiers: list[DeliveryTierCreate] | None = None
    opening_hours: list[OpeningHoursCreate] | None = None

    @field_validator("subscription_plan")
    @classmethod
    def validate_subscription_plan(cls, value: str | None) -> str | None:
        return _normalize_subscription_plan(value)

#Data returned when fetching a restaurant
class RestaurantResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str
    timezone: str = "Europe/Paris"
    address: AddressResponse | None = None
    stripe_id: str | None = None
    stripe_charges_enabled: bool = False
    stripe_payouts_enabled: bool = False
    stripe_details_submitted: bool = False
    subscription_plan: str
    subscription_interval: str = "month"
    subscription_status: str | None = None
    subscription_cancel_at_period_end: bool = False
    subscription_current_period_ends_at: datetime | None = None
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    has_tablet_rental: bool = False
    has_printer_rental: bool = False
    ai_monthly_quota: int
    ai_usage_count: int
    ai_monthly_token_quota: int
    ai_token_usage_count: int
    ai_cycle_started_at: datetime | None = None
    created_at: datetime
    config: RestaurantConfigResponse | None = None
    delivery_tiers: list[DeliveryTierResponse] = []
    opening_hours: list[OpeningHoursResponse] = []

    class Config:
        from_attributes = True


class RestaurantSubscriptionUpdate(BaseModel):
    subscription_plan: str
    subscription_interval: str | None = None
    has_tablet_rental: bool | None = None
    has_printer_rental: bool | None = None
    ai_cycle_started_at: datetime | None = None

    @field_validator("subscription_plan")
    @classmethod
    def validate_subscription_plan(cls, value: str) -> str:
        normalized = _normalize_subscription_plan(value)
        assert normalized is not None
        return normalized

    @field_validator("subscription_interval")
    @classmethod
    def validate_subscription_interval(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in {"month", "year"}:
            raise ValueError("subscription_interval must be 'month' or 'year'")
        return normalized


class RestaurantSubscriptionUsage(BaseModel):
    plan: str
    interval: str
    subscription_status: str | None = None
    subscription_display_status: str
    subscription_cancel_at_period_end: bool = False
    subscription_current_period_ends_at: datetime | None = None
    subscription_next_billing_at: datetime | None = None
    has_tablet_rental: bool = False
    has_printer_rental: bool = False
    monthly_quota: int
    usage_count: int
    usage_remaining: int
    monthly_token_quota: int
    token_usage_count: int
    token_usage_remaining: int
    cycle_started_at: datetime | None = None
    cycle_ends_at: datetime | None = None
    is_ai_enabled: bool
    is_quota_reached: bool
    is_token_quota_reached: bool
    upgrade_message: str | None = None
