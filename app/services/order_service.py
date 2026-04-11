import random
import string
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.customer import Customer
from app.models.address import Address
from app.models.product import Product
from app.models.menu import Menu
from app.models.menu_option import MenuOption
from app.models.all_you_can_eat import AllYouCanEat
from app.schemas.order import OrderCreate


def generate_order_number(first_name: str) -> str:
    letter = first_name[0].upper()
    digits = "".join(random.choices(string.digits, k=4))
    return f"#{letter}{digits}"


def create_order(db: Session, restaurant_id: int, data: OrderCreate) -> Order:
    # 1. Create customer (not required for onsite)
    customer_id = None
    if data.type != "onsite":
        if not data.customer:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer is required for delivery and pickup orders")
        customer = Customer(restaurant_id=restaurant_id, **data.customer.model_dump())
        db.add(customer)
        db.flush()
        customer_id = customer.id

    # 2. Create address if delivery
    address_id = None
    if data.type == "delivery":
        if not data.address:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Address is required for delivery orders")
        address = Address(**data.address.model_dump())
        db.add(address)
        db.flush()
        address_id = address.id

    # 3. Generate unique order number
    first_name = data.customer.first_name if data.customer else "X"
    order_number = generate_order_number(first_name)
    while db.query(Order).filter(Order.order_number == order_number).first():
        order_number = generate_order_number(first_name)

    # 4. Process items and calculate total
    amount_total = 0
    processed_items = []

    for item in data.items:
        if item.product_id:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise HTTPException(status_code=400, detail=f"Product {item.product_id} not found")
            unit_price = float(product.price)
            subtotal = unit_price * item.quantity
            amount_total += subtotal
            processed_items.append({
                "product_id": item.product_id,
                "name": product.name,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "comment": item.comment,
                "options": []
            })

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
            amount_total += subtotal
            processed_items.append({
                "menu_id": item.menu_id,
                "name": menu.name,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "comment": item.comment,
                "options": options
            })

        elif item.all_you_can_eat_id:
            ayce = db.query(AllYouCanEat).filter(AllYouCanEat.id == item.all_you_can_eat_id).first()
            if not ayce:
                raise HTTPException(status_code=400, detail=f"AllYouCanEat offer {item.all_you_can_eat_id} not found")
            unit_price = float(ayce.price)
            subtotal = unit_price * item.quantity
            amount_total += subtotal
            processed_items.append({
                "all_you_can_eat_id": item.all_you_can_eat_id,
                "name": ayce.name,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "comment": item.comment,
                "options": []
            })

        else:
            raise HTTPException(status_code=400, detail="Each item must have a product_id, menu_id, or all_you_can_eat_id")

    # 5. Vérifier que la table existe et appartient au restaurant
    if data.table_id:
        from app.models.table import Table
        table = db.query(Table).filter(Table.id == data.table_id, Table.restaurant_id == restaurant_id).first()
        if not table:
            raise HTTPException(status_code=400, detail=f"Table {data.table_id} not found for this restaurant")

    # 6. Create order
    order = Order(
        order_number=order_number,
        restaurant_id=restaurant_id,
        customer_id=customer_id,
        type=data.type,
        comment=data.comment,
        requested_time=data.requested_time,
        table_id=data.table_id,
        address_id=address_id,
        amount_total=amount_total
    )
    db.add(order)
    db.flush()

    # 7. Create order items
    for item_data in processed_items:
        options = item_data.pop("options")
        order_item = OrderItem(order_id=order.id, **item_data)
        db.add(order_item)
        db.flush()

        for option in options:
            child = OrderItem(
                order_id=order.id,
                menu_option_id=option.id,
                name=option.name,
                quantity=order_item.quantity,
                unit_price=float(option.additional_price),
                subtotal=float(option.additional_price) * order_item.quantity,
                parent_order_item_id=order_item.id
            )
            db.add(child)

    db.commit()
    db.refresh(order)
    return order
