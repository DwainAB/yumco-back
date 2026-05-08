from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db.database import Base


class RestaurantAnnouncement(Base):
    __tablename__ = "restaurant_announcements"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String, nullable=False)  # info | promotion | new_menu | exceptional_closure | warning
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    display_scope = Column(String, nullable=False, default="all")  # home | cart | reservation | all
    priority = Column(Integer, nullable=False, default=0)
    start_at = Column(DateTime(timezone=True), nullable=True)
    end_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
