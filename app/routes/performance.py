from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.performance_analytics import PerformanceAnalyticsResponse
from app.services.performance_analytics_service import get_performance_analytics


router = APIRouter(prefix="/restaurants", tags=["performance"])


@router.get("/{restaurant_id}/performance/analytics", response_model=PerformanceAnalyticsResponse)
def get_restaurant_performance_analytics(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analytics = get_performance_analytics(db, restaurant_id)
    if analytics is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return analytics
