from pydantic import BaseModel, HttpUrl, field_validator

from app.schemas.restaurant import ALLOWED_SUBSCRIPTION_PLANS


class StripeSubscriptionCheckoutRequest(BaseModel):
    subscription_plan: str
    subscription_interval: str
    has_tablet_rental: bool = False
    has_printer_rental: bool = False
    success_url: HttpUrl
    cancel_url: HttpUrl

    @field_validator("subscription_plan")
    @classmethod
    def validate_subscription_plan(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_SUBSCRIPTION_PLANS:
            raise ValueError(f"subscription_plan must be one of: {', '.join(sorted(ALLOWED_SUBSCRIPTION_PLANS))}")
        return normalized

    @field_validator("subscription_interval")
    @classmethod
    def validate_subscription_interval(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"month", "year"}:
            raise ValueError("subscription_interval must be 'month' or 'year'")
        return normalized


class StripeSubscriptionCheckoutResponse(BaseModel):
    checkout_session_id: str
    checkout_url: HttpUrl


class StripeCustomerPortalRequest(BaseModel):
    return_url: HttpUrl


class StripeCustomerPortalResponse(BaseModel):
    url: HttpUrl


class StripeSubscriptionUpdateRequest(BaseModel):
    subscription_plan: str
    subscription_interval: str
    has_tablet_rental: bool = False
    has_printer_rental: bool = False

    @field_validator("subscription_plan")
    @classmethod
    def validate_subscription_plan(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_SUBSCRIPTION_PLANS:
            raise ValueError(f"subscription_plan must be one of: {', '.join(sorted(ALLOWED_SUBSCRIPTION_PLANS))}")
        return normalized

    @field_validator("subscription_interval")
    @classmethod
    def validate_subscription_interval(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"month", "year"}:
            raise ValueError("subscription_interval must be 'month' or 'year'")
        return normalized


class StripeInvoiceResponse(BaseModel):
    id: str
    status: str | None = None
    currency: str | None = None
    total: int | None = None
    hosted_invoice_url: HttpUrl | None = None
    invoice_pdf: HttpUrl | None = None
    created: int
