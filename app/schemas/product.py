from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

class CategoryInfo(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    price: Decimal
    image_url: str | None = None
    category_id: int | None = None
    is_available: bool = True
    available_online: bool = True
    available_onsite: bool = True
    group: str | None = None

class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = None
    image_url: str | None = None
    category_id: int | None = None
    is_available: bool | None = None
    available_online: bool | None = None
    available_onsite: bool | None = None
    group: str | None = None

class ProductResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    price: Decimal
    image_url: str | None = None
    category: CategoryInfo | None = None
    restaurant_id: int
    is_available: bool
    available_online: bool
    available_onsite: bool
    group: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True
