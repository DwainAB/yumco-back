import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.services.review_followup_service import process_due_review_followups

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/review-followups/process")
def process_review_followups_route(
    limit: int = Query(default=100, ge=1, le=500),
    x_cron_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not settings.REVIEW_FOLLOWUPS_CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="REVIEW_FOLLOWUPS_CRON_SECRET is not configured",
        )
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.REVIEW_FOLLOWUPS_CRON_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid cron secret")
    return process_due_review_followups(db, limit=limit)
