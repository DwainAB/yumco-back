from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.customer_analytics import CustomerAnalyticsResponse
from app.services.customer_analytics_service import get_customer_analytics


router = APIRouter(prefix="/restaurants", tags=["customer-analytics"])


@router.get("/{restaurant_id}/customers/analytics", response_model=CustomerAnalyticsResponse)
def get_restaurant_customer_analytics(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analytics = get_customer_analytics(db, restaurant_id)
    if analytics is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return analytics
