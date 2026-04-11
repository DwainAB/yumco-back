from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.revenue_analytics import RevenueAnalyticsResponse
from app.services.revenue_analytics_service import get_revenue_analytics


router = APIRouter(prefix="/restaurants", tags=["revenue"])


@router.get("/{restaurant_id}/revenue/analytics", response_model=RevenueAnalyticsResponse)
def get_restaurant_revenue_analytics(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analytics = get_revenue_analytics(db, restaurant_id)
    if analytics is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return analytics
