from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.restaurant import RestaurantCreate, RestaurantResponse, RestaurantUpdate
from app.services.restaurant_service import get_restaurant, get_restaurants_by_user, create_restaurant, update_restaurant, delete_restaurant
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/restaurants", tags=["restaurants"])

@router.get("/", response_model=list[RestaurantResponse])
def get_my_restaurants(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_restaurants_by_user(db, current_user.id)

@router.get("/{restaurant_id}", response_model=RestaurantResponse)
def get_restaurant_by_id(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    restaurant = get_restaurant(db, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return restaurant

@router.post("/", response_model=RestaurantResponse, status_code=status.HTTP_201_CREATED)
def create(data: RestaurantCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return create_restaurant(db, data)

@router.put("/{restaurant_id}", response_model=RestaurantResponse)
def update(restaurant_id: int, data: RestaurantUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    restaurant = get_restaurant(db, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return update_restaurant(db, restaurant, data)

@router.delete("/{restaurant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    restaurant = get_restaurant(db, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    delete_restaurant(db, restaurant)
