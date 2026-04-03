from sqlalchemy import String, Integer, Column, ForeignKey, UniqueConstraint
from app.db.database import Base

class Role(Base):
    __tablename__="roles"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)

    # One user can only have one role per restaurant
    __table_args__ = (UniqueConstraint("user_id", "restaurant_id"),)