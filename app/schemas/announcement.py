from datetime import datetime

from pydantic import BaseModel, field_validator


ALLOWED_ANNOUNCEMENT_TYPES = {"info", "promotion", "new_menu", "exceptional_closure", "warning"}
ALLOWED_DISPLAY_SCOPES = {"home", "cart", "reservation", "all"}


def _normalize_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_ANNOUNCEMENT_TYPES:
        raise ValueError(f"type must be one of: {', '.join(sorted(ALLOWED_ANNOUNCEMENT_TYPES))}")
    return normalized


def _normalize_scope(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_DISPLAY_SCOPES:
        raise ValueError(f"display_scope must be one of: {', '.join(sorted(ALLOWED_DISPLAY_SCOPES))}")
    return normalized


class AnnouncementBase(BaseModel):
    type: str
    title: str
    message: str
    display_scope: str = "all"
    priority: int = 0
    start_at: datetime | None = None
    end_at: datetime | None = None
    is_active: bool = True

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        return _normalize_type(value)

    @field_validator("display_scope")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return _normalize_scope(value)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title is required")
        return normalized

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message is required")
        return normalized

    @field_validator("end_at")
    @classmethod
    def validate_dates(cls, value: datetime | None, info) -> datetime | None:
        start_at = info.data.get("start_at")
        if value and start_at and value <= start_at:
            raise ValueError("end_at must be after start_at")
        return value


class AnnouncementCreate(AnnouncementBase):
    pass


class AnnouncementUpdate(BaseModel):
    type: str | None = None
    title: str | None = None
    message: str | None = None
    display_scope: str | None = None
    priority: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    is_active: bool | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_type(value)

    @field_validator("display_scope")
    @classmethod
    def validate_scope(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_scope(value)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("title is required")
        return normalized

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("message is required")
        return normalized


class AnnouncementResponse(AnnouncementBase):
    id: int
    restaurant_id: int
    created_at: datetime

    class Config:
        from_attributes = True
