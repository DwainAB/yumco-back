from pydantic import BaseModel, EmailStr
from datetime import datetime

class RoleInfo(BaseModel):
    restaurant_id: int
    type: str

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone : str | None = None
    restaurant_id: int
    role: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    phone: str | None = None
    created_at: datetime
    expo_push_token: str | None = None
    is_admin: bool = False
    roles: list[RoleInfo] = []

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    expo_push_token: str | None = None
    email : EmailStr | None = None
    password : str | None = None
    role: str | None = None