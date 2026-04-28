import random
import string
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.address import Address
from app.models.all_you_can_eat import AllYouCanEat
from app.models.customer import Customer
from app.models.delivery_tiers import DeliveryTier
from app.models.menu import Menu
from app.models.menu_option import MenuOption
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.restaurant import Restaurant
from app.schemas.order import OrderCreate
from app.services.geo_service import _haversine, geocode_address_sync


MONEY_QUANT = Decimal("0.01")


def _money(value: float | int | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _build_full_address(address: Address) -> str:
    return f"{address.street}, {address.postal_code} {address.city}, {address.country}"


def _serialize_tier(tier: DeliveryTier) -> dict:
    return {
        "min_km": tier.min_km,
        "max_km": tier.max_km,
        "price": float(tier.price),
        "min_order_amount": float(tier.min_order_amount),
    }


def _sum_root_item_subtotals(order: Order) -> Decimal:
    return _money(
        sum(
            _money(item.subtotal)
            for item in order.items
            if item.parent_order_item_id is None
        )
    )


def generate_order_number(first_name: str) -> str:
    letter = first_name[0].upper()
    digits = "".join(random.choices(string.digits, k=4))
    return f"#{letter}{digits}"


def resolve_delivery_quote(
    restaurant: Restaurant,
    customer_address: Address,
    items_subtotal: Decimal,
) -> dict:
    if not restaurant.address:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Restaurant address is not configured")

    try:
        restaurant_point = geocode_address_sync(_build_full_address(restaurant.address))
        customer_point = geocode_address_sync(_build_full_address(customer_address))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to calculate delivery distance") from exc

    distance_km = _haversine(
        restaurant_point["lat"],
        restaurant_point["lng"],
        customer_point["lat"],
        customer_point["lng"],
    )
    rounded_distance = round(distance_km, 2)

    if restaurant.config and restaurant.config.max_delivery_km is not None and distance_km > restaurant.config.max_delivery_km:
        return {
            "eligible": False,
            "items_subtotal": float(items_subtotal),
            "delivery_fee": 0.0,
            "amount_total": float(items_subtotal),
            "distance_km": rounded_distance,
            "shortfall_amount": 0.0,
            "next_min_order_amount": None,
            "message": "Adresse hors zone de livraison",
            "applied_tier": None,
        }

    tiers = list(restaurant.delivery_tiers or [])
    if not tiers:
        return {
            "eligible": True,
            "items_subtotal": float(items_subtotal),
            "delivery_fee": 0.0,
            "amount_total": float(items_subtotal),
            "distance_km": rounded_distance,
            "shortfall_amount": 0.0,
            "next_min_order_amount": None,
            "message": "Livraison disponible",
            "applied_tier": None,
        }

    distance_matching_tiers = [
        tier
        for tier in tiers
        if tier.min_km <= distance_km <= tier.max_km
    ]
    if not distance_matching_tiers:
        return {
            "eligible": False,
            "items_subtotal": float(items_subtotal),
            "delivery_fee": 0.0,
            "amount_total": float(items_subtotal),
            "distance_km": rounded_distance,
            "shortfall_amount": 0.0,
            "next_min_order_amount": None,
            "message": "Aucun tarif de livraison n'est configure pour cette distance",
            "applied_tier": None,
        }

    eligible_tiers = [
        tier
        for tier in distance_matching_tiers
        if items_subtotal >= _money(tier.min_order_amount)
    ]
    if not eligible_tiers:
        next_threshold = min(_money(tier.min_order_amount) for tier in distance_matching_tiers)
        shortfall = (next_threshold - items_subtotal).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        return {
            "eligible": False,
            "items_subtotal": float(items_subtotal),
            "delivery_fee": 0.0,
            "amount_total": float(items_subtotal),
            "distance_km": rounded_distance,
            "shortfall_amount": float(shortfall),
            "next_min_order_amount": float(next_threshold),
            "message": f"Livraison disponible a partir de {float(next_threshold):.2f} EUR pour votre zone",
            "applied_tier": None,
        }

    selected_tier = max(
        eligible_tiers,
        key=lambda tier: (_money(tier.min_order_amount), -_money(tier.price), -(tier.max_km - tier.min_km)),
    )
    delivery_fee = _money(selected_tier.price)
    amount_total = (items_subtotal + delivery_fee).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    return {
        "eligible": True,
        "items_subtotal": float(items_subtotal),
        "delivery_fee": float(delivery_fee),
        "amount_total": float(amount_total),
        "distance_km": rounded_distance,
        "shortfall_amount": 0.0,
        "next_min_order_amount": None,
        "message": "Livraison disponible",
        "applied_tier": _serialize_tier(selected_tier),
    }


def recalculate_order_delivery_totals(db: Session, order: Order) -> None:
    items_subtotal = _sum_root_item_subtotals(order)
    order.items_subtotal = items_subtotal

    if order.type != "delivery" or order.address is None:
        order.delivery_fee = Decimal("0.00")
        order.delivery_distance_km = None
        order.amount_total = items_subtotal
        return

    restaurant = db.query(Restaurant).filter(Restaurant.id == order.restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    quote = resolve_delivery_quote(restaurant, order.address, items_subtotal)
    if not quote["eligible"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=quote["message"])

    order.delivery_fee = _money(quote["delivery_fee"])
    order.delivery_distance_km = _money(quote["distance_km"])
    order.amount_total = _money(quote["amount_total"])


def create_order(db: Session, restaurant_id: int, data: OrderCreate) -> Order:
    customer_id = None
    if data.type != "onsite":
        if not data.customer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer is required for delivery and pickup orders",
            )
        customer = Customer(restaurant_id=restaurant_id, **data.customer.model_dump())
        db.add(customer)
        db.flush()
        customer_id = customer.id

    address = None
    address_id = None
    if data.type == "delivery":
        if not data.address:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Address is required for delivery orders")
        address = Address(**data.address.model_dump())
        db.add(address)
        db.flush()
        address_id = address.id

    first_name = data.customer.first_name if data.customer else "X"
    order_number = generate_order_number(first_name)
    while db.query(Order).filter(Order.order_number == order_number).first():
        order_number = generate_order_number(first_name)

    items_subtotal = Decimal("0.00")
    processed_items = []

    for item in data.items:
        if item.product_id:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise HTTPException(status_code=400, detail=f"Product {item.product_id} not found")
            unit_price = float(product.price)
            subtotal = unit_price * item.quantity
            items_subtotal += _money(subtotal)
            processed_items.append(
                {
                    "product_id": item.product_id,
                    "name": product.name,
                    "quantity": item.quantity,
                    "unit_price": unit_price,
                    "subtotal": subtotal,
                    "comment": item.comment,
                    "options": [],
                }
            )

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
            items_subtotal += _money(subtotal)
            processed_items.append(
                {
                    "menu_id": item.menu_id,
                    "name": menu.name,
                    "quantity": item.quantity,
                    "unit_price": unit_price,
                    "subtotal": subtotal,
                    "comment": item.comment,
                    "options": options,
                }
            )

        elif item.all_you_can_eat_id:
            ayce = db.query(AllYouCanEat).filter(AllYouCanEat.id == item.all_you_can_eat_id).first()
            if not ayce:
                raise HTTPException(status_code=400, detail=f"AllYouCanEat offer {item.all_you_can_eat_id} not found")
            unit_price = float(ayce.price)
            subtotal = unit_price * item.quantity
            items_subtotal += _money(subtotal)
            processed_items.append(
                {
                    "all_you_can_eat_id": item.all_you_can_eat_id,
                    "name": ayce.name,
                    "quantity": item.quantity,
                    "unit_price": unit_price,
                    "subtotal": subtotal,
                    "comment": item.comment,
                    "options": [],
                }
            )

        else:
            raise HTTPException(status_code=400, detail="Each item must have a product_id, menu_id, or all_you_can_eat_id")

    if data.table_id:
        from app.models.table import Table

        table = db.query(Table).filter(Table.id == data.table_id, Table.restaurant_id == restaurant_id).first()
        if not table:
            raise HTTPException(status_code=400, detail=f"Table {data.table_id} not found for this restaurant")
        if data.type == "onsite":
            table.is_available = False

    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    delivery_fee = Decimal("0.00")
    delivery_distance_km = None
    if data.type == "delivery" and address is not None:
        quote = resolve_delivery_quote(restaurant, address, items_subtotal)
        if not quote["eligible"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=quote["message"])
        delivery_fee = _money(quote["delivery_fee"])
        delivery_distance_km = _money(quote["distance_km"])

    amount_total = items_subtotal + delivery_fee
    order = Order(
        order_number=order_number,
        restaurant_id=restaurant_id,
        customer_id=customer_id,
        type=data.type,
        is_draft=(data.type == "onsite"),
        comment=data.comment,
        requested_time=data.requested_time,
        table_id=data.table_id,
        address_id=address_id,
        items_subtotal=items_subtotal,
        delivery_fee=delivery_fee,
        delivery_distance_km=delivery_distance_km,
        amount_total=amount_total,
    )
    db.add(order)
    db.flush()

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
                parent_order_item_id=order_item.id,
            )
            db.add(child)

    db.commit()
    db.refresh(order)
    return order
