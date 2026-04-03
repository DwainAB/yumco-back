from pydantic import BaseModel, EmailStr
from datetime import datetime

#Data required to create a restaurant
class RestaurantCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str

#Data for updating a restaurant
class RestaurantUpdate(BaseModel):
    name: str | None = None
    email : EmailStr | None = None
    phone : str | None = None
    stripe_id: str | None = None

#Data returned when fetching a restaurant
class RestaurantResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str
    stripe_id: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True