from pydantic import BaseModel
from datetime import datetime

class TableCreate(BaseModel):
    table_number: str
    number_of_people: int
    is_available: bool = True
    location: str | None = None
    temporary: bool = False

class TableUpdate(BaseModel):
    table_number: str | None = None
    number_of_people: int | None = None
    is_available: bool | None = None
    location: str | None = None
    temporary: bool | None = None

class TableResponse(BaseModel):
    id: int
    restaurant_id: int
    table_number: str
    number_of_people: int
    is_available: bool
    location: str | None = None
    temporary: bool
    created_at: datetime

    class Config:
        from_attributes = True
