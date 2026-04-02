from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

#create the SLQAlchemy engine (the connection to PostgreSQL)
engine = create_engine(settings.DATABASE_URL)

#Each request gets its own session (like a temporary conversation with the DB)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

#Base class that all models will inherit from
class Base(DeclarativeBase):
    pass

#Dependency - gives a DB session to a route, then closes it automatically
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()