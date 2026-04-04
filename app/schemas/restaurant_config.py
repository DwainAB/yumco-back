from pydantic import BaseModel

class RestaurantConfigResponse(BaseModel):
    id: int
    restaurant_id: int
    accept_orders: bool
    preparation_time: int
    midday_delivery: bool
    evening_delivery: bool
    pickup: bool
    onsite: bool
    reservation: bool
    all_you_can_eat: bool
    a_la_carte: bool
    payment_online: bool
    payment_onsite: bool

    class Config:
        from_attributes = True

class RestaurantConfigUpdate(BaseModel):
    accept_orders: bool | None = None
    preparation_time: int | None = None
    midday_delivery: bool | None = None
    evening_delivery: bool | None = None
    pickup: bool | None = None
    onsite: bool | None = None
    reservation: bool | None = None
    all_you_can_eat: bool | None = None
    a_la_carte: bool | None = None
    payment_online: bool | None = None
    payment_onsite: bool | None = None