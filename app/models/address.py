from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    street = Column(String, nullable=False)
    city = Column(String, nullable=False)
    postal_code = Column(String, nullable=False)
    country = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
