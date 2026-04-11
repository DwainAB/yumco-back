from sqlalchemy.orm import Session
from app.models.restaurant import Restaurant
from app.models.role import Role
from app.schemas.restaurant import RestaurantCreate, RestaurantUpdate
from app.models.address import Address
from app.models.restaurant_config import RestaurantConfig
from app.models.delivery_tiers import DeliveryTier
from app.models.opening_hours import OpeningHours
from app.services.subscription_service import PLAN_LIMITS, PLAN_TOKEN_LIMITS, apply_subscription_plan


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
    #Create address first
    address = Address(
        street=data.address.street,
        city=data.address.city,
        postal_code=data.address.postal_code,
        country=data.address.country
    )
    db.add(address)
    db.commit()
    db.refresh(address)

    selected_plan = data.subscription_plan or "starter"

    restaurant = Restaurant(
        name=data.name,
        email=data.email,
        phone=data.phone,
        address_id=address.id,
        subscription_plan=selected_plan,
        ai_monthly_quota=PLAN_LIMITS[selected_plan],
        ai_usage_count=0,
        ai_monthly_token_quota=PLAN_TOKEN_LIMITS[selected_plan],
        ai_token_usage_count=0,
    )
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)

    config_data = data.config.model_dump(exclude_unset=True) if data.config else {}
    config = RestaurantConfig(restaurant_id=restaurant.id, **config_data)
    db.add(config)
    db.commit()
    db.refresh(restaurant)

    if data.delivery_tiers:
        for tier in data.delivery_tiers:
            db.add(DeliveryTier(restaurant_id=restaurant.id, **tier.model_dump()))
        db.commit()
        db.refresh(restaurant)
    
    if data.opening_hours:
        for hours in data.opening_hours:
            db.add(OpeningHours(restaurant_id=restaurant.id, **hours.model_dump()))
        db.commit()
        db.refresh(restaurant)
        
    return restaurant

#Delete a restaurant
def delete_restaurant(db: Session, restaurant: Restaurant):
    restaurant.is_deleted = True
    db.commit()


#Update a restaurant
def update_restaurant(db: Session, restaurant: Restaurant, data: RestaurantUpdate):
    update_data = data.model_dump(exclude_unset=True)

    if data.address:
        address = db.query(Address).filter(Address.id == restaurant.address_id).first()
        if address:
            for field, value in data.address.model_dump(exclude_unset=True).items():
                setattr(address, field, value)

    if data.config:
        config = db.query(RestaurantConfig).filter(RestaurantConfig.restaurant_id == restaurant.id).first()
        if config:
            for field, value in data.config.model_dump(exclude_unset=True).items():
                setattr(config, field, value)

    if data.delivery_tiers is not None:
        db.query(DeliveryTier).filter(DeliveryTier.restaurant_id == restaurant.id).delete()
        for tier in data.delivery_tiers:
            db.add(DeliveryTier(restaurant_id=restaurant.id, **tier.model_dump()))

    if data.opening_hours is not None:
        db.query(OpeningHours).filter(OpeningHours.restaurant_id == restaurant.id).delete()
        for hours in data.opening_hours:
            db.add(OpeningHours(restaurant_id=restaurant.id, **hours.model_dump()))

    for field, value in update_data.items():
        if field not in ["address", "config", "delivery_tiers", "opening_hours", "subscription_plan"]:
            setattr(restaurant, field, value)

    db.commit()
    db.refresh(restaurant)

    if "subscription_plan" in update_data:
        return apply_subscription_plan(db, restaurant, update_data["subscription_plan"], update_data.get("ai_cycle_started_at"))

    return restaurant
