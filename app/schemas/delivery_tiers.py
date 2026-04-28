from pydantic import BaseModel, Field, model_validator
from decimal import Decimal

class DeliveryTierCreate(BaseModel):
    min_km: int = Field(ge=0)
    max_km: int = Field(ge=0)
    price: Decimal = Field(ge=0)
    min_order_amount: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def validate_range(self):
        if self.max_km < self.min_km:
            raise ValueError("max_km must be greater than or equal to min_km")
        return self

class DeliveryTierResponse(BaseModel):
    id: int
    min_km: int
    max_km: int
    price: Decimal
    min_order_amount: Decimal

    class Config:
        from_attributes = True
