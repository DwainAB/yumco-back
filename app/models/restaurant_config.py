from sqlalchemy import Column, Integer, Boolean, ForeignKey
from app.db.database import Base

class RestaurantConfig(Base):
    __tablename__="restaurant_configs"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Orders 
    accept_orders = Column(Boolean, default=False)
    preparation_time = Column(Integer, default=30)

    # Delivery options
    midday_delivery = Column(Boolean, default=True)
    evening_delivery = Column(Boolean, default=True)

    # Services
    pickup = Column(Boolean, default=True)
    onsite = Column(Boolean, default=True)
    reservation = Column(Boolean, default=True)

    # Dining options
    all_you_can_eat = Column(Boolean, default=False)
    a_la_carte = Column(Boolean, default=True)

    # Payment options
    payment_online = Column(Boolean, default=False)
    payment_onsite = Column(Boolean, default=False)

    # Delivery zone
    max_delivery_km = Column(Integer, nullable=True)