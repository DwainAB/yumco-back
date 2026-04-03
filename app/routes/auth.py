from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.user import UserCreate, UserResponse, UserLogin, UserUpdate
from app.services.user_service import get_user_by_email, get_user_by_id, create_user, update_user, delete_user
from app.core.security import verify_password, create_access_token, get_current_user
from app.models.user import User
from app.models.role import Role

router = APIRouter(prefix="/auth", tags=["auth"])

# Register a new user
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db:Session = Depends(get_db)):
    existing_user = get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    return create_user(db, user)

#Login and get access token
@router.post("/login")
def login(user:UserLogin, db:Session = Depends(get_db)):
    db_user = get_user_by_email(db, user.email)
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    token = create_access_token(data={"sub": db_user.email})
    return {"access_token" : token, "token_type": "bearer"}


@router.get('/me', response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user

#Update current user
@router.put('/me', response_model=UserResponse)
def update_me(data: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return update_user(db, current_user, data, current_user)

#Delete current user
@router.delete('/me', status_code=status.HTTP_204_NO_CONTENT)
def delete_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    delete_user(db, current_user)

# Update a user (owner or manager only)
@router.put("/users/{user_id}", response_model=UserResponse)
def update_user_by_id(user_id: int, data: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_role = db.query(Role).filter(Role.user_id == current_user.id).first()
    if not current_role or current_role.type not in ["owner", "manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return update_user(db, user, data, current_user)

# Delete a user (owner or manager only)
@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_by_id(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_role = db.query(Role).filter(Role.user_id == current_user.id).first()
    if not current_role or current_role.type not in ["owner", "manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    delete_user(db, user)
