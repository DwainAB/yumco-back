from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.user import User
from app.models.restaurant import Restaurant
from app.schemas.user import UserResponse, UserUpdate
from app.schemas.restaurant import RestaurantResponse
from app.services.user_service import get_user_by_id, update_user, delete_user
from app.core.security import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])

def require_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user

# Get all users
@router.get("/users", response_model=list[UserResponse])
def get_all_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).all()

# Get one user
@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

# Update a user
@router.put("/users/{user_id}", response_model=UserResponse)
def admin_update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return update_user(db, user, data, current_user)

# Delete a user
@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    delete_user(db, user)

# Get all restaurants
@router.get("/restaurants", response_model=list[RestaurantResponse])
def get_all_restaurants(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(Restaurant).filter(Restaurant.is_deleted == False).all()

# Delete a restaurant (hard delete)
@router.delete("/restaurants/{restaurant_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_restaurant(restaurant_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    db.delete(restaurant)
    db.commit()