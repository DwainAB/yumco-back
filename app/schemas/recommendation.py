from decimal import Decimal

from pydantic import BaseModel, Field


class RecommendationBasketItem(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)


class RecommendationRequest(BaseModel):
    items: list[RecommendationBasketItem]
    limit: int = Field(default=3, ge=1, le=10)


class RecommendedProduct(BaseModel):
    product_id: int
    name: str
    price: Decimal
    image_url: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    score: float
    reason: str


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendedProduct]
