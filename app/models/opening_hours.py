from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.db.database import Base

class OpeningHours(Base):
    __tablename__ = "opening_hours"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    day = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    lunch_open = Column(String, nullable=True)
    lunch_close = Column(String, nullable=True)
    dinner_open = Column(String, nullable=True)
    dinner_close = Column(String, nullable=True)
    is_closed = Column(Boolean, default=False)