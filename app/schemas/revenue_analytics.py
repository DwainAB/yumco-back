from pydantic import BaseModel


class RevenuePeak(BaseModel):
    label: str | None = None
    amount: float


class RevenueChannel(BaseModel):
    amount: float
    percentage: float


class YearlyRevenueChannels(BaseModel):
    year: int
    delivery: RevenueChannel
    pickup: RevenueChannel


class MonthlyRevenueItem(BaseModel):
    month: str
    amount: float
    annual_percentage: float


class YearlyRevenueBreakdown(BaseModel):
    year: int
    total_amount: float
    months: list[MonthlyRevenueItem]


class RevenueAverageBasket(BaseModel):
    amount: float
    change_percentage_vs_previous_month: float | None = None


class RevenueAnalyticsResponse(BaseModel):
    current_month_amount: float
    current_month_change_percentage: float | None = None
    previous_month_amount: float
    yearly_channels: list[YearlyRevenueChannels]
    best_month: RevenuePeak
    best_day: RevenuePeak
    yearly_breakdown: list[YearlyRevenueBreakdown]
    annual_growth_percentage: float | None = None
    average_basket: RevenueAverageBasket
