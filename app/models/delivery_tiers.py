from sqlalchemy import Column, Integer, Numeric, ForeignKey
from app.db.database import Base

class DeliveryTier(Base):
    __tablename__= "delivery_tiers"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    min_km = Column(Integer, nullable=False)
    max_km = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)