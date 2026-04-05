from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

class AllYouCanEatCreate(BaseModel):
    name: str
    price: Decimal

class AllYouCanEatUpdate(BaseModel):
    name: str | None = None
    price: Decimal | None = None

class AllYouCanEatResponse(BaseModel):
    id: int
    restaurant_id: int
    name: str
    price: Decimal
    created_at: datetime

    class Config:
        from_attributes = True
