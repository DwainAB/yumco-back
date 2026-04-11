from datetime import datetime
from pydantic import BaseModel


class AnalyticsItemPerformance(BaseModel):
    item_name: str
    item_type: str
    quantity_sold: int
    revenue: float


class AnalyticsDeliveryCity(BaseModel):
    city: str
    orders_count: int


class AnalyticsMonthPeak(BaseModel):
    label: str | None = None
    orders_count: int


class AnalyticsLargestOrder(BaseModel):
    amount: float
    created_at: datetime


class AnalyticsAverageBasket(BaseModel):
    amount: float
    change_percentage_vs_previous_year: float | None = None


class AnalyticsWeekdayStat(BaseModel):
    day: str
    orders_count: int


class AnalyticsTimeSlot(BaseModel):
    slot: str | None = None
    orders_count: int


class AnalyticsRepeatPurchase(BaseModel):
    rate_percentage: float | None = None
    repeat_customers: int
    identifiable_customers: int


class OrderAnalyticsResponse(BaseModel):
    top_items: list[AnalyticsItemPerformance]
    monthly_orders_count: int
    monthly_orders_change: int
    monthly_orders_change_percentage: float | None = None
    monthly_revenue_change_percentage: float | None = None
    delivery_percentage: float
    pickup_percentage: float
    top_delivery_cities: list[AnalyticsDeliveryCity]
    best_month: AnalyticsMonthPeak
    largest_order: AnalyticsLargestOrder | None = None
    current_year_orders_count: int
    average_basket: AnalyticsAverageBasket
    busiest_days: list[AnalyticsWeekdayStat]
    busiest_time_slot: AnalyticsTimeSlot
    repeat_purchase: AnalyticsRepeatPurchase
