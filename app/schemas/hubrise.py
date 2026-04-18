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


class HubriseOrderLogResponse(BaseModel):
    id: int
    status: str
    hubrise_location_id: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HubriseOrderDebugResponse(BaseModel):
    restaurant_id: int
    order_id: int
    order_type: str
    order_status: str
    is_draft: bool
    hubrise_order_id: str | None = None
    hubrise_raw_status: str | None = None
    hubrise_sync_status: str | None = None
    hubrise_last_error: str | None = None
    hubrise_synced_at: datetime | None = None
    latest_log: HubriseOrderLogResponse | None = None
