from pydantic import BaseModel
from datetime import datetime

class CategoryCreate(BaseModel):
    name: str

class CategoryUpdate(BaseModel):
    name: str | None = None

class CategoryResponse(BaseModel):
    id: int
    name: str
    restaurant_id: int
    created_at: datetime

    class Config:
        from_attributes = True
