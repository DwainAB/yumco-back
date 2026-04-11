from pydantic import BaseModel


class PreparationTimeOverview(BaseModel):
    average_minutes: float
    difference_vs_previous_month_minutes: float


class PreparerPerformance(BaseModel):
    user_id: int
    first_name: str
    prepared_orders_count: int
    average_preparation_minutes: float


class PerformanceAnalyticsResponse(BaseModel):
    preparation_time: PreparationTimeOverview
    preparers: list[PreparerPerformance]
