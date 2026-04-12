from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, nullable=False)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    type = Column(String, nullable=False)  # delivery | pickup | onsite
    status = Column(String, default="pending")  # pending | preparing | completed | cancelled
    payment_status = Column(String, default="unpaid")  # unpaid | awaiting_payment | paid | refunded
    amount_total = Column(Numeric(10, 2), nullable=False, default=0)
    stripe_checkout_session_id = Column(String, nullable=True)
    stripe_payment_intent_id = Column(String, nullable=True)
    stripe_charge_id = Column(String, nullable=True)
    comment = Column(String, nullable=True)
    requested_time = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    address_id = Column(Integer, ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True)
    table_id = Column(Integer, ForeignKey("tables.id", ondelete="SET NULL"), nullable=True)
    preparing_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship("OrderItem", cascade="all, delete-orphan")
    customer = relationship("Customer")
    address = relationship("Address")
    prepared_by_user = relationship("User", foreign_keys=[preparing_by])
