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
    stripe_charges_enabled = Column(Boolean, nullable=False, default=False)
    stripe_payouts_enabled = Column(Boolean, nullable=False, default=False)
    stripe_details_submitted = Column(Boolean, nullable=False, default=False)
    timezone=Column(String, nullable=False, default="Europe/Paris")
    subscription_plan = Column(String, nullable=False, default="starter")
    subscription_interval = Column(String, nullable=False, default="month")
    subscription_status = Column(String, nullable=True)
    subscription_cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    subscription_current_period_ends_at = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    has_tablet_rental = Column(Boolean, nullable=False, default=False)
    has_printer_rental = Column(Boolean, nullable=False, default=False)
    ai_monthly_quota = Column(Integer, nullable=False, default=0)
    ai_usage_count = Column(Integer, nullable=False, default=0)
    ai_monthly_token_quota = Column(Integer, nullable=False, default=0)
    ai_token_usage_count = Column(Integer, nullable=False, default=0)
    ai_cycle_started_at = Column(DateTime(timezone=True), nullable=True)
    is_deleted=Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    config = relationship("RestaurantConfig", uselist=False)
    hubrise_connection = relationship("HubriseConnection", uselist=False, back_populates="restaurant")
    hubrise_order_logs = relationship("HubriseOrderLog", back_populates="restaurant")
    delivery_tiers = relationship("DeliveryTier")
    opening_hours = relationship("OpeningHours")
