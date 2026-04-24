from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import extract
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.hubrise_connection import HubriseConnection
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.restaurant_config import RestaurantConfig
from app.models.table import Table
from app.models.opening_hours import OpeningHours
from app.schemas.order import OrderCreate, OrderItemCreate, OrderSubmitResponse, OrderUpdate, OrderResponse, OrderStatusUpdate
from app.schemas.order_analytics import OrderAnalyticsResponse
from app.core.security import get_current_user
from app.models.user import User
from app.services.order_analytics_service import get_order_analytics
from app.services.order_service import create_order
from app.services.receipt_service import generate_receipt
from app.services.hubrise_service import sync_order_items_to_hubrise, sync_order_status_to_hubrise, sync_order_to_hubrise
from app.services.order_email_service import (
    send_order_confirmed,
    send_order_preparing,
    send_order_completed,
    send_order_cancelled,
)
from app.services.notification_service import notify_new_order
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

router = APIRouter(prefix="/restaurants", tags=["orders"])

@router.get("/{restaurant_id}/orders/slots")
def get_order_slots(
    restaurant_id: int,
    type: str = Query(..., description="pickup or delivery"),
    date_str: str = Query(default=None, alias="date", description="YYYY-MM-DD, defaults to today"),
    db: Session = Depends(get_db)
):
    if type not in ("pickup", "delivery"):
        raise HTTPException(status_code=400, detail="type must be 'pickup' or 'delivery'")

    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    tz = ZoneInfo(restaurant.timezone or "Europe/Paris")
    now = datetime.now(tz)

    target_date: date = date.fromisoformat(date_str) if date_str else now.date()

    # 0=Monday ... 6=Sunday 
    weekday = target_date.weekday()
    hours = db.query(OpeningHours).filter(
        OpeningHours.restaurant_id == restaurant_id,
        OpeningHours.day == weekday
    ).first()

    if not hours or hours.is_closed:
        return {"asap": False, "slots": []}

    # Collect open windows: lunch and/or dinner
    windows = []
    for open_str, close_str in [
        (hours.lunch_open, hours.lunch_close),
        (hours.dinner_open, hours.dinner_close),
    ]:
        if open_str and close_str:
            open_dt = datetime.fromisoformat(f"{target_date}T{open_str}").replace(tzinfo=tz)
            close_dt = datetime.fromisoformat(f"{target_date}T{close_str}").replace(tzinfo=tz)
            windows.append((open_dt, close_dt))

    if not windows:
        return {"asap": False, "slots": []}

    # delivery: last slot is 30min before closing
    cutoff_delta = timedelta(minutes=30) if type == "delivery" else timedelta(0)
    # Minimum lead time: 30min from now
    earliest = now + timedelta(minutes=30)
    # Round up earliest to next 15min mark
    minutes_mod = earliest.minute % 15
    if minutes_mod != 0:
        earliest += timedelta(minutes=15 - minutes_mod)
    earliest = earliest.replace(second=0, microsecond=0)

    slots = []
    for open_dt, close_dt in windows:
        last_slot = close_dt - cutoff_delta
        cursor = max(open_dt, earliest)
        # Round cursor up to next 15min mark
        minutes_mod = cursor.minute % 15
        if minutes_mod != 0:
            cursor += timedelta(minutes=15 - minutes_mod)
        cursor = cursor.replace(second=0, microsecond=0)
        while cursor <= last_slot:
            slots.append(cursor.isoformat())
            cursor += timedelta(minutes=15)

    # asap = True if restaurant is currently open
    asap = any(open_dt <= now <= close_dt for open_dt, close_dt in windows)

    return {"asap": asap, "slots": slots}


@router.post("/{restaurant_id}/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_route(restaurant_id: int, data: OrderCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    restaurant_config = db.query(RestaurantConfig).filter(RestaurantConfig.restaurant_id == restaurant_id).first()
    if restaurant_config and restaurant_config.payment_online and not restaurant_config.payment_onsite:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Online payment is required for this restaurant")
    order = create_order(db, restaurant_id, data)
    if order.is_draft:
        return order
    hubrise_connection = None
    if order.type in {"pickup", "delivery"}:
        hubrise_connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == restaurant_id).first()
        if hubrise_connection:
            order.hubrise_sync_status = "pending"
            order.hubrise_last_error = None
            db.commit()
            db.refresh(order)
            print(
                "[hubrise] scheduling order sync",
                {"order_id": order.id, "restaurant_id": restaurant_id, "location_id": hubrise_connection.hubrise_location_id},
            )
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    background_tasks.add_task(send_order_confirmed, order, restaurant)
    background_tasks.add_task(notify_new_order, restaurant_id, order.order_number)
    if hubrise_connection:
        background_tasks.add_task(sync_order_to_hubrise, order.id)
    return order


@router.post("/{restaurant_id}/orders/{order_id}/submit", response_model=OrderSubmitResponse)
def submit_onsite_order(
    restaurant_id: int,
    order_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.type != "onsite":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only onsite orders can be submitted")
    if not order.is_draft:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order is already submitted")

    order.is_draft = False
    db.commit()
    db.refresh(order)

    hubrise_connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == restaurant_id).first()
    if hubrise_connection:
        order.hubrise_sync_status = "pending"
        order.hubrise_last_error = None
        db.commit()
        db.refresh(order)
        print(
            "[hubrise] scheduling onsite order sync",
            {"order_id": order.id, "restaurant_id": restaurant_id, "location_id": hubrise_connection.hubrise_location_id},
        )
        background_tasks.add_task(sync_order_to_hubrise, order.id)

    background_tasks.add_task(notify_new_order, restaurant_id, order.order_number)
    return order

@router.get("/{restaurant_id}/orders", response_model=list[OrderResponse])
def list_orders(
    restaurant_id: int,
    table_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Order).filter(Order.restaurant_id == restaurant_id)
    if table_id is not None:
        q = q.filter(Order.table_id == table_id)
    if status_filter is not None:
        q = q.filter(Order.status == status_filter)
    if month is not None:
        q = q.filter(extract("month", Order.created_at) == month)
    if year is not None:
        q = q.filter(extract("year", Order.created_at) == year)
    return q.order_by(Order.created_at.desc()).all()


@router.get("/{restaurant_id}/orders/analytics", response_model=OrderAnalyticsResponse)
def get_orders_analytics(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    analytics = get_order_analytics(db, restaurant_id)
    if analytics is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return analytics

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
    if order.is_draft and new_status is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Draft onsite orders must be submitted before changing status")

    if new_status == "preparing" and "preparing_by" not in update_data:
        update_data["preparing_by"] = current_user.id

    if new_status == "completed" and not order.completed_at:
        from datetime import datetime, timezone
        update_data["completed_at"] = datetime.now(timezone.utc)

    if new_status in {"completed", "cancelled"} and order.table_id:
        table = db.query(Table).filter(Table.id == order.table_id).first()
        if table:
            table.is_available = True

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
        if order.hubrise_order_id:
            background_tasks.add_task(sync_order_status_to_hubrise, order.id, new_status)

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


@router.post("/{restaurant_id}/orders/{order_id}/status", response_model=OrderResponse)
def update_order_status(restaurant_id: int, order_id: int, data: OrderStatusUpdate, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.is_draft:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Draft onsite orders must be submitted before changing status")

    order.status = data.status

    if data.status == "preparing":
        order.preparing_by = data.preparing_by or current_user.id
    elif data.status == "completed":
        from datetime import datetime, timezone
        order.completed_at = datetime.now(timezone.utc)
    if data.status in {"completed", "cancelled"} and order.table_id:
        table = db.query(Table).filter(Table.id == order.table_id).first()
        if table:
            table.is_available = True

    db.commit()
    db.refresh(order)

    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()

    if data.status == "preparing":
        background_tasks.add_task(send_order_preparing, order, restaurant, data.preparation_time)
    elif data.status == "completed":
        background_tasks.add_task(send_order_completed, order, restaurant)
    elif data.status == "cancelled":
        background_tasks.add_task(send_order_cancelled, order, restaurant)
    if order.hubrise_order_id:
        background_tasks.add_task(sync_order_status_to_hubrise, order.id, data.status)

    return order


@router.post("/{restaurant_id}/orders/{order_id}/items", response_model=OrderResponse)
def add_order_items(
    restaurant_id: int,
    order_id: int,
    items: list[OrderItemCreate],
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.order_item import OrderItem
    from app.models.product import Product
    from app.models.menu import Menu
    from app.models.menu_option import MenuOption
    from app.models.all_you_can_eat import AllYouCanEat

    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    added_total = 0

    for item in items:
        if item.product_id:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise HTTPException(status_code=400, detail=f"Product {item.product_id} not found")
            unit_price = float(product.price)
            existing = db.query(OrderItem).filter(
                OrderItem.order_id == order.id,
                OrderItem.product_id == item.product_id,
                OrderItem.parent_order_item_id == None
            ).first()
            if existing:
                existing.quantity += item.quantity
                existing.subtotal = float(existing.unit_price) * existing.quantity
                added_total += unit_price * item.quantity
            else:
                subtotal = unit_price * item.quantity
                added_total += subtotal
                db.add(OrderItem(order_id=order.id, product_id=item.product_id, name=product.name, quantity=item.quantity, unit_price=unit_price, subtotal=subtotal, comment=item.comment))

        elif item.menu_id:
            menu = db.query(Menu).filter(Menu.id == item.menu_id).first()
            if not menu:
                raise HTTPException(status_code=400, detail=f"Menu {item.menu_id} not found")
            unit_price = float(menu.price)
            options = []
            for option_id in item.selected_options:
                option = db.query(MenuOption).filter(MenuOption.id == option_id).first()
                if not option:
                    raise HTTPException(status_code=400, detail=f"MenuOption {option_id} not found")
                unit_price += float(option.additional_price)
                options.append(option)
            subtotal = unit_price * item.quantity
            added_total += subtotal
            order_item = OrderItem(order_id=order.id, menu_id=item.menu_id, name=menu.name, quantity=item.quantity, unit_price=unit_price, subtotal=subtotal, comment=item.comment)
            db.add(order_item)
            db.flush()
            for option in options:
                db.add(OrderItem(order_id=order.id, menu_option_id=option.id, name=option.name, quantity=item.quantity, unit_price=float(option.additional_price), subtotal=float(option.additional_price) * item.quantity, parent_order_item_id=order_item.id))

        elif item.all_you_can_eat_id:
            ayce = db.query(AllYouCanEat).filter(AllYouCanEat.id == item.all_you_can_eat_id).first()
            if not ayce:
                raise HTTPException(status_code=400, detail=f"AllYouCanEat {item.all_you_can_eat_id} not found")
            unit_price = float(ayce.price)
            existing = db.query(OrderItem).filter(
                OrderItem.order_id == order.id,
                OrderItem.all_you_can_eat_id == item.all_you_can_eat_id,
                OrderItem.parent_order_item_id == None
            ).first()
            if existing:
                existing.quantity += item.quantity
                existing.subtotal = float(existing.unit_price) * existing.quantity
                added_total += unit_price * item.quantity
            else:
                subtotal = unit_price * item.quantity
                added_total += subtotal
                db.add(OrderItem(order_id=order.id, all_you_can_eat_id=item.all_you_can_eat_id, name=ayce.name, quantity=item.quantity, unit_price=unit_price, subtotal=subtotal, comment=item.comment))

        else:
            raise HTTPException(status_code=400, detail="Each item must have a product_id, menu_id, or all_you_can_eat_id")

    order.amount_total = float(order.amount_total) + added_total
    db.commit()
    db.refresh(order)
    if order.type == "onsite" and order.hubrise_order_id:
        background_tasks.add_task(sync_order_items_to_hubrise, order.id)
    return order


@router.delete("/{restaurant_id}/orders/{order_id}/items/{item_id}", response_model=OrderResponse)
def remove_order_item(
    restaurant_id: int,
    order_id: int,
    item_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.order_item import OrderItem

    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    item = db.query(OrderItem).filter(OrderItem.id == item_id, OrderItem.order_id == order_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    child_items = []
    if item.parent_order_item_id is None:
        child_items = db.query(OrderItem).filter(OrderItem.parent_order_item_id == item.id).all()

    if item.quantity > 1:
        item.quantity -= 1
        item.subtotal = float(item.unit_price) * item.quantity
        order.amount_total = float(order.amount_total) - float(item.unit_price)
        for child in child_items:
            child.quantity = item.quantity
            child.subtotal = float(child.unit_price) * child.quantity
    else:
        order.amount_total = float(order.amount_total) - float(item.subtotal)
        for child in child_items:
            db.delete(child)
        db.delete(item)

    db.commit()
    db.refresh(order)
    if order.type == "onsite" and order.hubrise_order_id:
        background_tasks.add_task(sync_order_items_to_hubrise, order.id)
    return order


@router.delete("/{restaurant_id}/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(restaurant_id: int, order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.restaurant_id == restaurant_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.type == "onsite" and not order.is_draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Submitted onsite orders must be cancelled instead of deleted",
        )
    if order.table_id:
        table = db.query(Table).filter(Table.id == order.table_id).first()
        if table:
            table.is_available = True
    db.delete(order)
    db.commit()
