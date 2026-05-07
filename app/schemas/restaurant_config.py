from pydantic import BaseModel, field_validator

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
    max_delivery_km: int | None = None
    printer_enabled: bool = False
    printer_name: str | None = None
    printer_host: str | None = None
    printer_port: int | None = None
    printer_paper_width: int | None = None

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
    max_delivery_km: int | None = None
    printer_enabled: bool | None = None
    printer_name: str | None = None
    printer_host: str | None = None
    printer_port: int | None = None
    printer_paper_width: int | None = None

    @field_validator("printer_paper_width")
    @classmethod
    def validate_printer_paper_width(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value not in (58, 80):
            raise ValueError("printer_paper_width must be 58 or 80")
        return value

    @field_validator("printer_port")
    @classmethod
    def validate_printer_port(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value <= 0 or value > 65535:
            raise ValueError("printer_port must be between 1 and 65535")
        return value
