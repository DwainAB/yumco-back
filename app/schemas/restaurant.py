from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.schemas.address import AddressCreate, AddressUpdate, AddressResponse
from app.schemas.restaurant_config import RestaurantConfigResponse, RestaurantConfigUpdate
from app.schemas.delivery_tiers import DeliveryTierCreate, DeliveryTierResponse
from app.schemas.opening_hours import OpeningHoursCreate, OpeningHoursResponse

#Data required to create a restaurant
class RestaurantCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str
    address: AddressCreate
    config: RestaurantConfigUpdate | None = None
    delivery_tiers: list[DeliveryTierCreate] | None = None
    opening_hours: list[OpeningHoursCreate] | None = None

#Data for updating a restaurant
class RestaurantUpdate(BaseModel):
    name: str | None = None
    email : EmailStr | None = None
    phone : str | None = None
    stripe_id: str | None = None
    address: AddressUpdate | None = None
    config: RestaurantConfigUpdate | None = None
    delivery_tiers: list[DeliveryTierCreate] | None = None
    opening_hours: list[OpeningHoursCreate] | None = None

#Data returned when fetching a restaurant
class RestaurantResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str
    address: AddressResponse | None = None
    stripe_id: str | None = None
    created_at: datetime
    config: RestaurantConfigResponse | None = None
    delivery_tiers: list[DeliveryTierResponse] = []
    opening_hours: list[OpeningHoursResponse] = []

    class Config:
        from_attributes = True