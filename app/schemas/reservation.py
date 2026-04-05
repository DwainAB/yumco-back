from pydantic import BaseModel, EmailStr
from datetime import date, time, datetime

class ReservationCreate(BaseModel):
    full_name: str
    email: EmailStr | None = None
    phone: str
    number_of_people: int
    reservation_date: date
    reservation_time: time
    comment: str | None = None

class ReservationUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    number_of_people: int | None = None
    reservation_date: date | None = None
    reservation_time: time | None = None
    comment: str | None = None
    status: str | None = None

class ReservationResponse(BaseModel):
    id: int
    restaurant_id: int
    full_name: str
    email: str | None = None
    phone: str
    number_of_people: int
    reservation_date: date
    reservation_time: time
    comment: str | None = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
