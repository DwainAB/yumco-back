from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.restaurant_announcement import RestaurantAnnouncement


def list_announcements(db: Session, restaurant_id: int) -> list[RestaurantAnnouncement]:
    return (
        db.query(RestaurantAnnouncement)
        .filter(RestaurantAnnouncement.restaurant_id == restaurant_id)
        .order_by(RestaurantAnnouncement.priority.desc(), RestaurantAnnouncement.created_at.desc())
        .all()
    )


def list_active_announcements(db: Session, restaurant_id: int) -> list[RestaurantAnnouncement]:
    now = datetime.now(timezone.utc)
    return (
        db.query(RestaurantAnnouncement)
        .filter(
            RestaurantAnnouncement.restaurant_id == restaurant_id,
            RestaurantAnnouncement.is_active.is_(True),
        )
        .filter((RestaurantAnnouncement.start_at.is_(None)) | (RestaurantAnnouncement.start_at <= now))
        .filter((RestaurantAnnouncement.end_at.is_(None)) | (RestaurantAnnouncement.end_at >= now))
        .order_by(RestaurantAnnouncement.priority.desc(), RestaurantAnnouncement.created_at.desc())
        .all()
    )


def get_announcement_by_id(db: Session, restaurant_id: int, announcement_id: int) -> RestaurantAnnouncement | None:
    return (
        db.query(RestaurantAnnouncement)
        .filter(
            RestaurantAnnouncement.restaurant_id == restaurant_id,
            RestaurantAnnouncement.id == announcement_id,
        )
        .first()
    )
