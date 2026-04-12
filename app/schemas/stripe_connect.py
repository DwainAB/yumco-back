from pydantic import BaseModel, HttpUrl

from app.schemas.order import OrderCreate


class StripeConnectAccountResponse(BaseModel):
    restaurant_id: int
    stripe_account_id: str | None = None
    onboarding_completed: bool
    charges_enabled: bool
    payouts_enabled: bool
    details_submitted: bool


class StripeConnectLinkRequest(BaseModel):
    return_url: HttpUrl | None = None
    refresh_url: HttpUrl | None = None


class StripeConnectLinkResponse(BaseModel):
    url: HttpUrl
    expires_at: int | None = None


class StripeCheckoutSessionRequest(BaseModel):
    success_url: HttpUrl
    cancel_url: HttpUrl


class StripeCheckoutSessionResponse(BaseModel):
    checkout_session_id: str
    checkout_url: HttpUrl


class StripeDraftCheckoutSessionRequest(BaseModel):
    success_url: HttpUrl
    cancel_url: HttpUrl
    order: OrderCreate
