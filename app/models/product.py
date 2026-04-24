from sqlalchemy import Column, Integer, String, Boolean, Numeric, ForeignKey, DateTime, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    image_url = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    is_available = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)
    available_online = Column(Boolean, default=True)
    available_onsite = Column(Boolean, default=True)
    group = Column(String, nullable=True)
    allergens = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("Category")
