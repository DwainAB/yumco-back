from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class MenuOption(Base):
    __tablename__ = "menu_options"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("menu_categories.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    name = Column(String, nullable=False)
    additional_price = Column(Numeric(10, 2), default=0)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
