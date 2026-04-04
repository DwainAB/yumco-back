from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

class MenuOptionCreate(BaseModel):
    name: str
    additional_price: Decimal = Decimal("0")
    display_order: int = 0
    product_id: int | None = None

class MenuOptionResponse(BaseModel):
    id: int
    name: str
    additional_price: Decimal
    display_order: int
    product_id: int | None = None

    class Config:
        from_attributes = True

class MenuCategoryCreate(BaseModel):
    name: str
    max_options: int = 1
    is_required: bool = True
    display_order: int = 0
    options: list[MenuOptionCreate] = []

class MenuCategoryResponse(BaseModel):
    id: int
    name: str
    max_options: int
    is_required: bool
    display_order: int
    options: list[MenuOptionResponse] = []

    class Config:
        from_attributes = True

class MenuCreate(BaseModel):
    name: str
    price: Decimal
    is_available: bool = True
    available_online: bool = True
    available_onsite: bool = True
    image_url: str | None = None
    categories: list[MenuCategoryCreate] = []

class MenuUpdate(BaseModel):
    name: str | None = None
    price: Decimal | None = None
    is_available: bool | None = None
    available_online: bool | None = None
    available_onsite: bool | None = None
    image_url: str | None = None
    categories: list[MenuCategoryCreate] | None = None

class MenuResponse(BaseModel):
    id: int
    restaurant_id: int
    name: str
    price: Decimal
    is_available: bool
    available_online: bool
    available_onsite: bool
    image_url: str | None = None
    created_at: datetime
    categories: list[MenuCategoryResponse] = []

    class Config:
        from_attributes = True
