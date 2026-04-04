from pydantic import BaseModel
from datetime import datetime

# Data required for creating an address
class AddressCreate(BaseModel):
    street: str
    city: str
    postal_code: str
    country: str

# Data returned when fetching an address
class AddressResponse(BaseModel):
    id: int
    street: str
    city: str
    postal_code: str
    country: str
    created_at: datetime

    class Config:
        from_attributes = True

# Data required for updating an address
class AddressUpdate(BaseModel):
    street: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None