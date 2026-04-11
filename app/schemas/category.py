from pydantic import BaseModel, field_validator
from datetime import datetime


ALLOWED_CATEGORY_KINDS = {"main", "starter", "drink", "side", "dessert", "other"}


def _normalize_kind(value: str | None) -> str | None:
    if value is None:
        return value
    normalized = value.strip().lower()
    if normalized not in ALLOWED_CATEGORY_KINDS:
        raise ValueError(f"kind must be one of: {', '.join(sorted(ALLOWED_CATEGORY_KINDS))}")
    return normalized


class CategoryCreate(BaseModel):
    name: str
    kind: str = "other"

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        normalized = _normalize_kind(value)
        assert normalized is not None
        return normalized


class CategoryUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str | None) -> str | None:
        return _normalize_kind(value)


class CategoryResponse(BaseModel):
    id: int
    name: str
    kind: str
    restaurant_id: int
    created_at: datetime

    class Config:
        from_attributes = True
