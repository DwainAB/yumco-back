from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.order import Order
from app.schemas.order import OrderCreate, OrderUpdate, OrderResponse
from app.core.security import get_current_user
from app.models.user import User
from app.services.order_service import create_order

router = APIRouter(prefix="/restaurants", tags=["orders"])

@router.post("/{restaurant_id}/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_route(restaurant_id: int, data: OrderCreate, db: Session = Depends(get_db)):
    return create_order(db, restaurant_id, data)

@router.get("/{restaurant_id}/orders", response_model=list[OrderResponse])
def list_orders(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.restaurant_id == restaurant_id).order_by(Order.created_at.desc()).all()

@router.get("/{restaurant_id}/orders/{order_id}", response_model=OrderResponse)
def get_order(restaurant_id: int, order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order

@router.put("/{restaurant_id}/orders/{order_id}", response_model=OrderResponse)
def update_order(restaurant_id: int, order_id: int, data: OrderUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    update_data = data.model_dump(exclude_unset=True)

    if update_data.get("status") == "preparing" and "preparing_by" not in update_data:
        update_data["preparing_by"] = current_user.id

    if update_data.get("status") == "completed" and not order.completed_at:
        from datetime import datetime, timezone
        update_data["completed_at"] = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(order, field, value)

    db.commit()
    db.refresh(order)
    return order

@router.delete("/{restaurant_id}/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(restaurant_id: int, order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    db.delete(order)
    db.commit()
