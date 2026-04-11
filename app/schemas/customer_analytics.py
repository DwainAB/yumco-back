from datetime import datetime
from pydantic import BaseModel


class CustomerCountOverview(BaseModel):
    total: int
    change_percentage_vs_previous_month: float | None = None


class LoyalCustomersOverview(BaseModel):
    total: int
    percentage_of_total_customers: float


class TopCustomerItem(BaseModel):
    identity: str
    first_name: str | None = None
    last_name: str | None = None
    orders_count: int
    total_spent: float
    last_order_at: datetime


class NewCustomersMonthlyItem(BaseModel):
    month: str
    count: int
    change_percentage_vs_previous_month: float | None = None


class NewCustomersYearlyBreakdown(BaseModel):
    year: int
    months: list[NewCustomersMonthlyItem]


class CustomerAnalyticsResponse(BaseModel):
    total_customers: CustomerCountOverview
    loyal_customers: LoyalCustomersOverview
    top_customers: list[TopCustomerItem]
    new_customers_breakdown: list[NewCustomersYearlyBreakdown]
