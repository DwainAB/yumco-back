from pydantic import BaseModel, HttpUrl


class StripeInvoiceResponse(BaseModel):
    id: str
    status: str | None = None
    currency: str | None = None
    total: int | None = None
    hosted_invoice_url: HttpUrl | None = None
    invoice_pdf: HttpUrl | None = None
    created: int


class StripeAdminSubscriptionLinksResponse(BaseModel):
    customer_url: HttpUrl | None = None
    subscription_url: HttpUrl | None = None
