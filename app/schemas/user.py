from pydantic import BaseModel, EmailStr, model_validator
from datetime import datetime

class RoleInfo(BaseModel):
    restaurant_id: int
    type: str

    class Config:
        from_attributes = True

class UserBrief(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone: str | None = None

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone : str | None = None
    restaurant_id: int | None = None
    role: str | None = None
    is_admin: bool = False

    @model_validator(mode="after")
    def validate_role_assignment(self):
        if (self.restaurant_id is None) != (self.role is None):
            raise ValueError("restaurant_id and role must be provided together")
        if self.is_admin and self.restaurant_id is not None:
            raise ValueError("admin users cannot be attached to a restaurant at creation")
        if not self.is_admin and self.restaurant_id is None:
            raise ValueError("non-admin users must be attached to a restaurant")
        return self

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
    notify_orders: bool = True
    notify_reservations: bool = True
    is_admin: bool = False
    roles: list[RoleInfo] = []

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    expo_push_token: str | None = None
    notify_orders: bool | None = None
    notify_reservations: bool | None = None
    email : EmailStr | None = None
    password : str | None = None
    role: str | None = None


class UserDeviceRegisterRequest(BaseModel):
    expo_push_token: str
    platform: str | None = None
    device_name: str | None = None


class UserDeviceUnregisterRequest(BaseModel):
    expo_push_token: str


class UserDeviceResponse(BaseModel):
    id: int
    expo_push_token: str
    platform: str | None = None
    device_name: str | None = None
    is_active: bool
    last_seen_at: datetime

    class Config:
        from_attributes = True
