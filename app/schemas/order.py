from pydantic import BaseModel
from datetime import datetime
from app.schemas.customer import CustomerCreate
from app.schemas.address import AddressCreate

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
    payment_status: str
    amount_total: float
    comment: str | None = None
    requested_time: datetime | None = None
    completed_at: datetime | None = None
    address_id: int | None = None
    table_id: int | None = None
    preparing_by: int | None = None
    items: list[OrderItemResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True
