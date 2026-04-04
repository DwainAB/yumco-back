from sqlalchemy import Column, Integer, String, Boolean, Numeric, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base

class Menu(Base):
    __tablename__ = "menus"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    is_available = Column(Boolean, default=True)
    available_online = Column(Boolean, default=True)
    available_onsite = Column(Boolean, default=True)
    image_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    categories = relationship("MenuCategory", cascade="all, delete-orphan")
