from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from app.schemas.customer import CustomerCreate, CustomerResponse
from app.schemas.address import AddressCreate, AddressResponse
from app.schemas.user import UserBrief

class OrderItemCreate(BaseModel):
    product_id: int | None = None
    menu_id: int | None = None
    all_you_can_eat_id: int | None = None
    quantity: int = 1
    comment: str | None = None
    selected_options: list[int] = []  # list of menu_option_ids (only if menu_id)

class OrderCreate(BaseModel):
    type: str  # delivery | pickup | onsite
    comment: str | None = None
    requested_time: datetime | None = None
    table_id: int | None = None
    address: AddressCreate | None = None  # required if type == delivery
    customer: CustomerCreate | None = None  # not required for onsite
    items: list[OrderItemCreate]


class DeliveryQuoteRequest(BaseModel):
    address: AddressCreate
    items_subtotal: Decimal = Field(ge=0)


class DeliveryQuoteTier(BaseModel):
    min_km: int
    max_km: int
    price: float
    min_order_amount: float


class DeliveryQuoteResponse(BaseModel):
    eligible: bool
    items_subtotal: float
    delivery_fee: float
    amount_total: float
    distance_km: float
    shortfall_amount: float = 0
    next_min_order_amount: float | None = None
    message: str
    applied_tier: DeliveryQuoteTier | None = None


class OrderStatusUpdate(BaseModel):
    status: str  # preparing | completed | cancelled
    preparing_by: int | None = None
    preparation_time: int | None = None  # minutes, pour l'email uniquement


class OrderReceiptEmailRequest(BaseModel):
    email: EmailStr | None = None


class OrderReceiptEmailResponse(BaseModel):
    message: str
    email: EmailStr


class OrderUpdate(BaseModel):
    status: str | None = None
    payment_status: str | None = None
    comment: str | None = None
    requested_time: datetime | None = None
    preparing_by: int | None = None

class OrderItemResponse(BaseModel):
    id: int
    order_id: int
    name: str
    quantity: int
    unit_price: float
    subtotal: float
    comment: str | None = None
    product_id: int | None = None
    menu_id: int | None = None
    menu_option_id: int | None = None
    all_you_can_eat_id: int | None = None
    parent_order_item_id: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True

class OrderResponse(BaseModel):
    id: int
    order_number: str
    restaurant_id: int
    customer_id: int | None = None
    type: str
    status: str
    is_draft: bool = False
    hubrise_raw_status: str | None = None
    payment_status: str
    items_subtotal: float = 0
    delivery_fee: float = 0
    delivery_distance_km: float | None = None
    amount_total: float
    comment: str | None = None
    requested_time: datetime | None = None
    completed_at: datetime | None = None
    address_id: int | None = None
    table_id: int | None = None
    preparing_by: int | None = None
    prepared_by_user: UserBrief | None = None
    customer: CustomerResponse | None = None
    address: AddressResponse | None = None
    items: list[OrderItemResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class OrderSubmitResponse(BaseModel):
    id: int
    status: str
    is_draft: bool

    class Config:
        from_attributes = True
