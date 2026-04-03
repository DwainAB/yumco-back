from sqlalchemy.orm import Session
from app.models.restaurant import Restaurant
from app.models.role import Role
from app.schemas.restaurant import RestaurantCreate, RestaurantUpdate


#Get all restaurants (Admin)
def get_all_restaurants(db: Session):
    return db.query(Restaurant).filter(Restaurant.is_deleted == False).all()

#Get all deleted restaurants (Admin)
def get_all_deleted_restaurant(db: Session):
    return db.query(Restaurant).filter(Restaurant.is_deleted == True).all()

#Get restaurant by id
def get_restaurant(db: Session, restaurant_id: int):
    return db.query(Restaurant).filter(Restaurant.id == restaurant_id, Restaurant.is_deleted == False).first()

#get all restaurants of a user (via roles)
def get_restaurants_by_user(db: Session, user_id: int):
    return db.query(Restaurant).join(Role).filter(Role.user_id == user_id, Restaurant.is_deleted == False).all()

#Create a restaurant
def create_restaurant(db: Session, data: RestaurantCreate):
    restaurant = Restaurant(
        name=data.name,
        email=data.email,
        phone=data.phone,
    )
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)
    return restaurant

#Delete a restaurant
def delete_restaurant(db: Session, restaurant: Restaurant):
    restaurant.is_deleted = True
    db.commit()


#Update a restaurant
def update_restaurant(db:Session, restaurant: Restaurant, data: RestaurantUpdate):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(restaurant, field, value)
    db.commit()
    db.refresh(restaurant)
    return restaurant
