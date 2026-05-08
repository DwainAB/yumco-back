from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.models.restaurant import Restaurant
from app.models.restaurant_announcement import RestaurantAnnouncement
from app.models.user import User
from app.schemas.announcement import AnnouncementCreate, AnnouncementResponse, AnnouncementUpdate
from app.services.announcement_service import get_announcement_by_id, list_active_announcements, list_announcements


router = APIRouter(prefix="/restaurants", tags=["announcements"])


def _get_restaurant_or_404(db: Session, restaurant_id: int) -> Restaurant:
    restaurant = (
        db.query(Restaurant)
        .filter(Restaurant.id == restaurant_id, Restaurant.is_deleted.is_(False))
        .first()
    )
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return restaurant


@router.get("/{restaurant_id}/announcements", response_model=list[AnnouncementResponse])
def get_restaurant_announcements(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_restaurant_or_404(db, restaurant_id)
    return list_announcements(db, restaurant_id)


@router.get("/{restaurant_id}/announcements/active", response_model=list[AnnouncementResponse])
def get_restaurant_active_announcements(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    _get_restaurant_or_404(db, restaurant_id)
    return list_active_announcements(db, restaurant_id)


@router.post("/{restaurant_id}/announcements", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
def create_restaurant_announcement(
    restaurant_id: int,
    data: AnnouncementCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_restaurant_or_404(db, restaurant_id)
    announcement = RestaurantAnnouncement(restaurant_id=restaurant_id, **data.model_dump())
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return announcement


@router.put("/{restaurant_id}/announcements/{announcement_id}", response_model=AnnouncementResponse)
def update_restaurant_announcement(
    restaurant_id: int,
    announcement_id: int,
    data: AnnouncementUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_restaurant_or_404(db, restaurant_id)
    announcement = get_announcement_by_id(db, restaurant_id, announcement_id)
    if not announcement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(announcement, field, value)

    db.commit()
    db.refresh(announcement)
    return announcement


@router.delete("/{restaurant_id}/announcements/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_restaurant_announcement(
    restaurant_id: int,
    announcement_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_restaurant_or_404(db, restaurant_id)
    announcement = get_announcement_by_id(db, restaurant_id, announcement_id)
    if not announcement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Announcement not found")
    db.delete(announcement)
    db.commit()
