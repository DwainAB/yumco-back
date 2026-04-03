from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class Restaurant(Base):
    __tablename__="restaurants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=False)
    address_id= Column(Integer, nullable=True)
    stripe_id=Column(String, nullable=True)
    is_deleted=Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())