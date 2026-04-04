from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.schemas.address import AddressCreate, AddressUpdate, AddressResponse

#Data required to create a restaurant
class RestaurantCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str
    address: AddressCreate

#Data for updating a restaurant
class RestaurantUpdate(BaseModel):
    name: str | None = None
    email : EmailStr | None = None
    phone : str | None = None
    stripe_id: str | None = None
    address: AddressUpdate | None = None

#Data returned when fetching a restaurant
class RestaurantResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str
    address: AddressResponse | None = None
    stripe_id: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True