from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.user import User
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.hubrise_connection import HubriseConnection
from app.models.role import Role
from app.schemas.user import UserResponse
from app.schemas.hubrise import HubriseRetryOrderResponse, HubriseTestOrderRequest, HubriseTestOrderResponse
from app.schemas.restaurant import RestaurantHubriseStatusResponse, RestaurantResponse
from app.services.user_service import get_user_by_id, delete_user
from app.services.hubrise_service import send_hubrise_test_order, sync_order_to_hubrise
from app.core.security import get_current_user
from datetime import datetime, timezone

router = APIRouter(prefix="/admin", tags=["admin"])

def require_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return current_user

@router.get("/users", response_model=list[UserResponse])
def get_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).all()

@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

@router.get("/restaurants", response_model=list[RestaurantResponse])
def get_all_restaurants(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(Restaurant).filter(Restaurant.is_deleted == False).all()

@router.get("/restaurants/deleted", response_model=list[RestaurantResponse])
def get_deleted_restaurants(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(Restaurant).filter(Restaurant.is_deleted == True).all()

@router.delete("/restaurants/{restaurant_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_restaurant(restaurant_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    db.delete(restaurant)
    db.commit()


@router.get("/restaurants/{restaurant_id}/hubrise/status", response_model=RestaurantHubriseStatusResponse)
def get_restaurant_hubrise_status(restaurant_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == restaurant_id).first()
    last_order = (
        db.query(Order)
        .filter(Order.restaurant_id == restaurant_id, Order.hubrise_order_id.isnot(None))
        .order_by(Order.hubrise_synced_at.desc().nullslast(), Order.id.desc())
        .first()
    )

    return RestaurantHubriseStatusResponse(
        connected=connection is not None,
        restaurant_id=restaurant_id,
        hubrise_account_id=connection.hubrise_account_id if connection else None,
        hubrise_location_id=connection.hubrise_location_id if connection else None,
        token_type=connection.token_type if connection else None,
        scope=connection.scope if connection else None,
        last_order_id=last_order.id if last_order else None,
        last_hubrise_order_id=last_order.hubrise_order_id if last_order else None,
        last_hubrise_raw_status=last_order.hubrise_raw_status if last_order else None,
        last_hubrise_sync_status=last_order.hubrise_sync_status if last_order else None,
        last_hubrise_error=last_order.hubrise_last_error if last_order else None,
        last_hubrise_synced_at=last_order.hubrise_synced_at if last_order else None,
    )


@router.post("/restaurants/{restaurant_id}/hubrise/test-order", response_model=HubriseTestOrderResponse)
async def send_restaurant_hubrise_test_order(
    restaurant_id: int,
    data: HubriseTestOrderRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    payload, response = await send_hubrise_test_order(db, restaurant_id, data)
    connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == restaurant_id).first()
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HubRise connection not found for this restaurant")

    return HubriseTestOrderResponse(
        connected=True,
        restaurant_id=restaurant_id,
        hubrise_location_id=connection.hubrise_location_id,
        payload=payload,
        response=response,
        sent_at=datetime.now(timezone.utc),
    )


@router.post("/restaurants/{restaurant_id}/hubrise/retry/orders/{order_id}", response_model=HubriseRetryOrderResponse)
def retry_restaurant_hubrise_order_sync(
    restaurant_id: int,
    order_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == restaurant_id).first()
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HubRise connection not found for this restaurant")

    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.type not in {"pickup", "delivery"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pickup and delivery orders can be retried on HubRise")

    order.hubrise_sync_status = "pending"
    order.hubrise_last_error = None
    db.commit()

    background_tasks.add_task(sync_order_to_hubrise, order.id)
    return HubriseRetryOrderResponse(
        restaurant_id=restaurant_id,
        order_id=order.id,
        hubrise_sync_status="pending",
        message="HubRise order sync retry scheduled",
    )
