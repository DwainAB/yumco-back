from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.db.database import Base
from sqlalchemy.orm import relationship

class Restaurant(Base):
    __tablename__="restaurants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=False)
    address_id= Column(Integer, ForeignKey("addresses.id"), nullable=True)
    address = relationship("Address")
    stripe_id=Column(String, nullable=True)
    timezone=Column(String, nullable=False, default="Europe/Paris")
    is_deleted=Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    config = relationship("RestaurantConfig", uselist=False)
    delivery_tiers = relationship("DeliveryTier")
    opening_hours = relationship("OpeningHours")
