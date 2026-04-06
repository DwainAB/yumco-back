from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.schemas.order import OrderCreate, OrderUpdate, OrderResponse
from app.core.security import get_current_user
from app.models.user import User
from app.services.order_service import create_order
from app.services.receipt_service import generate_receipt
from app.services.order_email_service import (
    send_order_confirmed,
    send_order_preparing,
    send_order_completed,
    send_order_cancelled,
)

router = APIRouter(prefix="/restaurants", tags=["orders"])

@router.post("/{restaurant_id}/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_route(restaurant_id: int, data: OrderCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    order = create_order(db, restaurant_id, data)
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    background_tasks.add_task(send_order_confirmed, order, restaurant)
    return order

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
def update_order(restaurant_id: int, order_id: int, data: OrderUpdate, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    update_data = data.model_dump(exclude_unset=True)
    new_status = update_data.get("status")

    if new_status == "preparing" and "preparing_by" not in update_data:
        update_data["preparing_by"] = current_user.id

    if new_status == "completed" and not order.completed_at:
        from datetime import datetime, timezone
        update_data["completed_at"] = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(order, field, value)

    db.commit()
    db.refresh(order)

    if new_status:
        restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
        if new_status == "preparing":
            background_tasks.add_task(send_order_preparing, order, restaurant)
        elif new_status == "completed":
            background_tasks.add_task(send_order_completed, order, restaurant)
        elif new_status == "cancelled":
            background_tasks.add_task(send_order_cancelled, order, restaurant)

    return order

@router.get("/{restaurant_id}/orders/{order_id}/receipt")
def get_receipt(restaurant_id: int, order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    pdf = generate_receipt(order, restaurant)
    filename = f"ticket_{order.order_number.replace('#', '')}.pdf"
    return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={filename}"})


@router.delete("/{restaurant_id}/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(restaurant_id: int, order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    db.delete(order)
    db.commit()
