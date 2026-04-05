from pydantic import BaseModel, EmailStr
from datetime import datetime

class CustomerCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone: str | None = None

class CustomerUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None

class CustomerResponse(BaseModel):
    id: int
    restaurant_id: int
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
