from pydantic import BaseModel
from decimal import Decimal

class DeliveryTierCreate(BaseModel):
    min_km: int
    max_km: int
    price: Decimal

class DeliveryTierResponse(BaseModel):
    id: int
    min_km: int
    max_km: int
    price: Decimal

    class Config:
        from_attributes = True