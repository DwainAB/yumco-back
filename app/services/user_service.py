from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.role import Role
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import hash_password

#Get a user by email
def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

# Get a user by id
def get_user_by_id(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()

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

    #Assign role to user
    role= Role(user_id=db_user.id, restaurant_id=user.restaurant_id, type=user.role)
    db.add(role)
    db.commit()
    return db_user

#update a user
def update_user(db: Session, user: User, data: UserUpdate, current_user: User):
    # Check if current_user has permission to change role
    if data.role:
        current_role = db.query(Role).filter(Role.user_id == current_user.id).first()
        if not current_role or current_role.type not in ["owner", "manager"]:
            raise HTTPException(status_code=403, detail="Not allowed to change roles")
        user_role = db.query(Role).filter(Role.user_id == user.id).first()
        if user_role:
            user_role.type = data.role
            db.commit()

    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "password":
            setattr(user, "hashed_password", hash_password(value))
        elif field != "role":
            setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user

#Delete a user
def delete_user(db: Session, user: User):
    db.delete(user)
    db.commit()