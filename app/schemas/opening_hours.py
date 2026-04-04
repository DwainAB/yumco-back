from pydantic import BaseModel

class OpeningHoursCreate(BaseModel):
    day: int
    lunch_open: str | None = None
    lunch_close: str | None = None
    dinner_open: str | None = None
    dinner_close: str | None = None
    is_closed: bool = False

class OpeningHoursResponse(BaseModel):
    id: int
    day: int
    lunch_open: str | None = None
    lunch_close: str | None = None
    dinner_open: str | None = None
    dinner_close: str | None = None
    is_closed: bool

    class Config:
        from_attributes = True