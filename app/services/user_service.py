from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import hash_password

#Get a user by email
def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

#Create a user
def create_user(db: Session, user: UserCreate):
    hashed = hash_password(user.password)
    db_user = User(
        email=user.email,
        hashed_password=hashed,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

#update a user
def update_user(db: Session, user: User, data: UserUpdate):
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "password":
            setattr(user, "hashed_password", hash_password(value))
        else:
            setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user

#Delete a user
def delete_user(db: Session, user: User):
    db.delete(user)
    db.commit()