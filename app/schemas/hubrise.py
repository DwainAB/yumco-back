from datetime import datetime
from typing import Literal, Any

from pydantic import BaseModel


class HubriseTestOrderRequest(BaseModel):
    order_type: Literal["pickup", "delivery"]
    is_paid: bool = False
    item_kind: Literal["product", "menu"] = "product"
    quantity: int = 1
    include_paid_option: bool = True
    include_free_option: bool = True


class HubriseTestOrderResponse(BaseModel):
    connected: bool
    restaurant_id: int
    hubrise_location_id: str
    payload: dict[str, Any]
    response: dict[str, Any]
    sent_at: datetime


class HubriseRetryOrderResponse(BaseModel):
    restaurant_id: int
    order_id: int
    hubrise_sync_status: str
    message: str
