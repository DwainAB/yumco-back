import json
import hmac
import hashlib
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.db.database import SessionLocal
from app.core.config import settings
from app.models.hubrise_connection import HubriseConnection
from app.models.hubrise_order_log import HubriseOrderLog
from app.models.menu import Menu
from app.models.menu_category import MenuCategory
from app.models.menu_option import MenuOption
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.restaurant import Restaurant
from app.models.table import Table
from app.schemas.hubrise import HubriseTestOrderRequest

HUBRISE_TOKEN_URL = "https://manager.hubrise.com/oauth2/v1/token"
HUBRISE_API_BASE_URL = "https://api.hubrise.com/v1"


def parse_restaurant_id_from_state(state: str | None) -> int:
    if not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing state")

    try:
        return int(state)
    except ValueError:
        pass

    try:
        payload = json.loads(state)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state") from exc

    restaurant_id = payload.get("restaurant_id")
    if not isinstance(restaurant_id, int):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")
    return restaurant_id


async def exchange_code_for_tokens(code: str) -> dict:
    if not settings.HUBRISE_CLIENT_ID or not settings.HUBRISE_CLIENT_SECRET:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="HubRise OAuth is not configured")

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.HUBRISE_REDIRECT_URI,
        "client_id": settings.HUBRISE_CLIENT_ID,
        "client_secret": settings.HUBRISE_CLIENT_SECRET,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(HUBRISE_TOKEN_URL, json=payload)

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HubRise token exchange failed ({response.status_code})",
        )

    data = response.json()
    if not data.get("access_token") or not data.get("location_id"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="HubRise response is missing required fields")

    return data


def save_hubrise_connection(db: Session, restaurant_id: int, token_data: dict) -> HubriseConnection:
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id, Restaurant.is_deleted.is_(False)).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == restaurant_id).first()
    if connection is None:
        connection = HubriseConnection(restaurant_id=restaurant_id)
        db.add(connection)

    connection.hubrise_location_id = token_data["location_id"]
    connection.hubrise_account_id = token_data.get("account_id") or token_data["location_id"]
    connection.access_token = token_data["access_token"]
    connection.refresh_token = token_data.get("refresh_token")
    connection.token_type = token_data.get("token_type") or "Bearer"
    connection.scope = token_data.get("scope") or ""

    db.commit()
    db.refresh(connection)
    return connection


async def register_hubrise_order_callback(connection: HubriseConnection) -> dict | None:
    if not settings.HUBRISE_WEBHOOK_URL:
        print("[hubrise] callback registration skipped", {"reason": "missing_webhook_url", "restaurant_id": connection.restaurant_id})
        return None

    payload = {
        "url": settings.HUBRISE_WEBHOOK_URL,
        "events": {
            "order": ["update"],
        },
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{HUBRISE_API_BASE_URL}/callback",
            json=payload,
            headers={
                "X-Access-Token": connection.access_token,
                "Content-Type": "application/json",
            },
        )

    response_data = response.json() if response.content else {}
    print(
        "[hubrise] callback registration",
        {
            "restaurant_id": connection.restaurant_id,
            "status_code": response.status_code,
            "response": response_data,
        },
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HubRise callback registration failed ({response.status_code})",
        )
    return response_data


def verify_hubrise_signature(raw_body: bytes, signature: str | None) -> bool:
    if not signature or not settings.HUBRISE_CLIENT_SECRET:
        return False
    expected = hmac.new(
        settings.HUBRISE_CLIENT_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def map_hubrise_status_to_yumco(hubrise_status: str | None, order_type: str | None = None) -> str | None:
    if hubrise_status in {"new", "received"}:
        return "pending"
    if order_type == "onsite" and hubrise_status in {"accepted", "in_preparation", "awaiting_collection", "in_delivery"}:
        return "pending"
    if hubrise_status in {"accepted", "in_preparation", "awaiting_collection", "in_delivery"}:
        return "preparing"
    if hubrise_status == "completed":
        return "completed"
    if hubrise_status in {"cancelled", "rejected", "delivery_failed"}:
        return "cancelled"
    return None


def apply_hubrise_order_update(db: Session, event_payload: dict) -> tuple[Order, str | None, str] | None:
    if event_payload.get("resource_type") != "order" or event_payload.get("event_type") != "update":
        return None

    new_state = event_payload.get("new_state") or {}
    hubrise_order_id = new_state.get("id") or event_payload.get("order_id")
    if not hubrise_order_id:
        print("[hubrise] order update ignored", {"reason": "missing_order_id", "payload": event_payload})
        return None

    order = db.query(Order).filter(Order.hubrise_order_id == hubrise_order_id).first()
    if order is None:
        private_ref = new_state.get("private_ref")
        if private_ref and str(private_ref).isdigit():
            order = db.query(Order).filter(Order.id == int(private_ref)).first()
    if order is None:
        print("[hubrise] order update ignored", {"reason": "order_not_found", "hubrise_order_id": hubrise_order_id})
        return None

    hubrise_status = new_state.get("status")
    yumco_status = map_hubrise_status_to_yumco(hubrise_status, order.type)
    previous_yumco_status = order.status

    order.hubrise_order_id = hubrise_order_id
    order.hubrise_raw_status = hubrise_status
    order.hubrise_sync_status = "sent"
    order.hubrise_last_error = None
    order.hubrise_synced_at = datetime.now(timezone.utc)

    if yumco_status:
        order.status = yumco_status
        if yumco_status == "completed" and not order.completed_at:
            order.completed_at = datetime.now(timezone.utc)
        if yumco_status in {"completed", "cancelled"} and order.table_id:
            table = db.query(Table).filter(Table.id == order.table_id).first()
            if table:
                table.is_available = True

    db.commit()
    db.refresh(order)
    print(
        "[hubrise] order status synced",
        {
            "order_id": order.id,
            "hubrise_order_id": hubrise_order_id,
            "hubrise_status": hubrise_status,
            "yumco_status": order.status,
        },
    )
    return order, previous_yumco_status, order.status


def _money(amount: float) -> str:
    return f"{amount:.2f} EUR"


def _service_type(order_type: str) -> str:
    if order_type == "pickup":
        return "collection"
    if order_type == "delivery":
        return "delivery"
    return "eat_in"


def _root_items(order: Order) -> list[OrderItem]:
    return [item for item in order.items if item.parent_order_item_id is None]


def _child_items_by_parent(order: Order) -> dict[int, list[OrderItem]]:
    grouped: dict[int, list[OrderItem]] = {}
    for item in order.items:
        if item.parent_order_item_id is None:
            continue
        grouped.setdefault(item.parent_order_item_id, []).append(item)
    return grouped


def build_hubrise_order_payload(order: Order, table_number: str | None = None) -> dict:
    child_items = _child_items_by_parent(order)
    items = []

    for item in _root_items(order):
        options = []
        for child in child_items.get(item.id, []):
            options.append(
                {
                    "option_list_name": "Customization",
                    "name": child.name,
                    "price": _money(float(child.unit_price)),
                    "quantity": child.quantity,
                }
            )

        item_payload = {
            "private_ref": str(item.id),
            "product_name": item.name,
            "price": _money(float(item.unit_price)),
            "quantity": str(item.quantity),
        }
        if item.comment:
            item_payload["customer_notes"] = item.comment
        if options:
            item_payload["options"] = options
        items.append(item_payload)

    customer_payload = None
    if order.type == "onsite" and table_number:
        customer_payload = {
            "first_name": "Table",
            "last_name": str(table_number),
        }
    elif order.customer:
        customer_payload = {
            "first_name": order.customer.first_name,
            "last_name": order.customer.last_name,
        }
        if order.customer.email:
            customer_payload["email"] = order.customer.email
        if order.customer.phone:
            customer_payload["phone"] = order.customer.phone
        if order.address:
            customer_payload["address_1"] = order.address.street
            customer_payload["postal_code"] = order.address.postal_code
            customer_payload["city"] = order.address.city
            customer_payload["country"] = order.address.country

    seller_notes: list[str] = []
    if table_number:
        seller_notes.append(f"Table {table_number}.")
    if order.payment_status == "paid":
        seller_notes.append("Commande deja payee sur Yumco.")
    else:
        seller_notes.append("Paiement a encaisser sur place.")

    payload = {
        "channel": "yumco",
        "ref": order.order_number,
        "private_ref": str(order.id),
        "status": "new",
        "service_type": _service_type(order.type),
        "asap": order.requested_time is None,
        "items": items,
        "seller_notes": " ".join(seller_notes),
    }
    if order.comment:
        payload["customer_notes"] = order.comment
    if order.requested_time:
        requested_time = order.requested_time
        if requested_time.tzinfo is None:
            requested_time = requested_time.replace(tzinfo=timezone.utc)
        payload["expected_time"] = requested_time.isoformat()
        if order.type == "delivery":
            payload["expected_time_pickup"] = False
    if customer_payload:
        payload["customer"] = customer_payload
    if order.payment_status == "paid":
        payload["payments"] = [
            {
                "name": "Yumco",
                "ref": "YUMCO",
                "amount": _money(float(order.amount_total)),
                "info": {"payment_status": order.payment_status},
            }
        ]

    return payload


def build_hubrise_order_patch_payload(order: Order, table_number: str | None = None) -> dict:
    base_payload = build_hubrise_order_payload(order, table_number=table_number)
    patch_items = []
    for item in base_payload["items"]:
        patch_item = {
            "product_name": item["product_name"],
            "price": item["price"],
            "quantity": item["quantity"],
        }
        if "customer_notes" in item:
            patch_item["customer_notes"] = item["customer_notes"]
        if "options" in item:
            patch_item["options"] = item["options"]
        patch_items.append(patch_item)
    patch_payload: dict = {
        "items": patch_items,
        "seller_notes": base_payload["seller_notes"],
    }
    if "customer_notes" in base_payload:
        patch_payload["customer_notes"] = base_payload["customer_notes"]
    if "payments" in base_payload:
        patch_payload["payments"] = base_payload["payments"]
    if "expected_time" in base_payload:
        patch_payload["expected_time"] = base_payload["expected_time"]
    if "expected_time_pickup" in base_payload:
        patch_payload["expected_time_pickup"] = base_payload["expected_time_pickup"]
    return patch_payload


def _create_hubrise_log(db: Session, order: Order, connection: HubriseConnection, payload: dict) -> HubriseOrderLog:
    log = HubriseOrderLog(
        order_id=order.id,
        restaurant_id=order.restaurant_id,
        hubrise_location_id=connection.hubrise_location_id,
        request_payload=payload,
        status="pending",
    )
    db.add(log)
    db.flush()
    return log


def _mark_order_sync_failure(order: Order, error_message: str) -> None:
    order.hubrise_sync_status = "failed"
    order.hubrise_last_error = error_message[:255]
    order.hubrise_synced_at = None


async def _post_hubrise_order(connection: HubriseConnection, payload: dict) -> tuple[int, dict]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{HUBRISE_API_BASE_URL}/location/orders",
            json=payload,
            headers={
                "X-Access-Token": connection.access_token,
                "Content-Type": "application/json",
            },
        )
    try:
        response_data = response.json() if response.content else {}
    except ValueError:
        response_data = {"raw_response": response.text}
    return response.status_code, response_data


def map_yumco_status_to_hubrise(yumco_status: str | None) -> str | None:
    if yumco_status == "preparing":
        return "accepted"
    if yumco_status == "completed":
        return "completed"
    if yumco_status == "cancelled":
        return "cancelled"
    return None


async def sync_order_to_hubrise(order_id: int) -> None:
    db = SessionLocal()
    try:
        print("[hubrise] sync started", {"order_id": order_id})
        order = (
            db.query(Order)
            .options(
                joinedload(Order.customer),
                joinedload(Order.address),
                joinedload(Order.items),
            )
            .filter(Order.id == order_id)
            .first()
        )
        if not order or order.type not in {"pickup", "delivery", "onsite"}:
            print("[hubrise] sync skipped", {"order_id": order_id, "reason": "order_missing_or_unsupported_type"})
            return

        connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == order.restaurant_id).first()
        if not connection:
            print("[hubrise] sync skipped", {"order_id": order_id, "reason": "no_connection"})
            return

        table_number = None
        if order.table_id:
            table = db.query(Table).filter(Table.id == order.table_id).first()
            if table:
                table_number = table.table_number

        payload = build_hubrise_order_payload(order, table_number=table_number)
        log = _create_hubrise_log(db, order, connection, payload)
        order.hubrise_sync_status = "pending"
        order.hubrise_last_error = None
        db.commit()
        print(
            "[hubrise] sending order",
            {
                "order_id": order_id,
                "location_id": connection.hubrise_location_id,
                "payload": payload,
            },
        )

        try:
            status_code, response_data = await _post_hubrise_order(connection, payload)
        except Exception as exc:
            db.rollback()
            order = db.query(Order).filter(Order.id == order_id).first()
            log = db.query(HubriseOrderLog).filter(HubriseOrderLog.id == log.id).first()
            error_message = f"HubRise request error: {exc}"
            if order and log:
                _mark_order_sync_failure(order, error_message)
                log.status = "failed"
                log.error_message = error_message
                db.commit()
            print(f"[hubrise] order sync failed for order {order_id}: {exc}")
            return

        print(
            "[hubrise] response received",
            {
                "order_id": order_id,
                "status_code": status_code,
                "response": response_data,
            },
        )

        order = db.query(Order).filter(Order.id == order_id).first()
        log = db.query(HubriseOrderLog).filter(HubriseOrderLog.id == log.id).first()
        if not order or not log:
            db.rollback()
            return

        log.response_payload = response_data
        if 200 <= status_code < 300:
            order.hubrise_order_id = response_data.get("id")
            order.hubrise_sync_status = "sent"
            order.hubrise_last_error = None
            order.hubrise_synced_at = datetime.now(timezone.utc)
            log.status = "sent"
        else:
            error_message = response_data.get("message") or response.text or "HubRise request failed"
            _mark_order_sync_failure(order, error_message)
            log.status = "failed"
            log.error_message = error_message

        db.commit()
    except Exception as exc:
        print(f"[hubrise] unexpected sync error for order {order_id}: {exc}")
        raise
    finally:
        db.close()


async def sync_order_status_to_hubrise(order_id: int, yumco_status: str) -> None:
    hubrise_status = map_yumco_status_to_hubrise(yumco_status)
    if not hubrise_status:
        return

    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order or not order.hubrise_order_id:
            print("[hubrise] status sync skipped", {"order_id": order_id, "reason": "missing_order_or_hubrise_id"})
            return

        connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == order.restaurant_id).first()
        if not connection:
            print("[hubrise] status sync skipped", {"order_id": order_id, "reason": "no_connection"})
            return

        payload = {"status": hubrise_status}
        print(
            "[hubrise] sending order status",
            {
                "order_id": order_id,
                "hubrise_order_id": order.hubrise_order_id,
                "yumco_status": yumco_status,
                "hubrise_status": hubrise_status,
            },
        )

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.patch(
                    f"{HUBRISE_API_BASE_URL}/location/orders/{order.hubrise_order_id}",
                    json=payload,
                    headers={
                        "X-Access-Token": connection.access_token,
                        "Content-Type": "application/json",
                    },
                )
        except Exception as exc:
            db.rollback()
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                order.hubrise_last_error = f"HubRise status sync error: {exc}"[:255]
                db.commit()
            print(f"[hubrise] status sync failed for order {order_id}: {exc}")
            return

        try:
            response_data = response.json() if response.content else {}
        except ValueError:
            response_data = {"raw_response": response.text}

        print(
            "[hubrise] status response received",
            {
                "order_id": order_id,
                "status_code": response.status_code,
                "response": response_data,
            },
        )

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            db.rollback()
            return

        if response.is_success:
            order.hubrise_raw_status = response_data.get("status", hubrise_status)
            order.hubrise_sync_status = "sent"
            order.hubrise_last_error = None
            order.hubrise_synced_at = datetime.now(timezone.utc)
        else:
            order.hubrise_last_error = (
                response_data.get("message") or response.text or "HubRise status sync failed"
            )[:255]
        db.commit()
    finally:
        db.close()


async def sync_order_items_to_hubrise(order_id: int) -> None:
    db = SessionLocal()
    try:
        order = (
            db.query(Order)
            .options(
                joinedload(Order.customer),
                joinedload(Order.address),
                joinedload(Order.items),
            )
            .filter(Order.id == order_id)
            .first()
        )
        if not order or not order.hubrise_order_id:
            print("[hubrise] order patch skipped", {"order_id": order_id, "reason": "missing_order_or_hubrise_id"})
            return

        connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == order.restaurant_id).first()
        if not connection:
            print("[hubrise] order patch skipped", {"order_id": order_id, "reason": "no_connection"})
            return

        table_number = None
        if order.table_id:
            table = db.query(Table).filter(Table.id == order.table_id).first()
            if table:
                table_number = table.table_number

        async with httpx.AsyncClient(timeout=20.0) as client:
            current_response = await client.get(
                f"{HUBRISE_API_BASE_URL}/location/orders/{order.hubrise_order_id}",
                headers={"X-Access-Token": connection.access_token},
            )

        try:
            current_order_data = current_response.json() if current_response.content else {}
        except ValueError:
            current_order_data = {"raw_response": current_response.text}

        if not current_response.is_success:
            order.hubrise_sync_status = "failed"
            order.hubrise_last_error = (
                current_order_data.get("message") or current_response.text or "HubRise order fetch failed"
            )[:255]
            db.commit()
            print(
                "[hubrise] order patch skipped",
                {
                    "order_id": order_id,
                    "reason": "fetch_failed",
                    "status_code": current_response.status_code,
                    "response": current_order_data,
                },
            )
            return

        payload = build_hubrise_order_patch_payload(order, table_number=table_number)
        existing_items = current_order_data.get("items") or []
        delete_ops = [
            {"id": item["id"], "deleted": True}
            for item in existing_items
            if item.get("id") and not item.get("deleted")
        ]
        payload["items"] = delete_ops + payload["items"]
        print(
            "[hubrise] sending order patch",
            {
                "order_id": order_id,
                "hubrise_order_id": order.hubrise_order_id,
                "payload": payload,
            },
        )

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.patch(
                    f"{HUBRISE_API_BASE_URL}/location/orders/{order.hubrise_order_id}",
                    json=payload,
                    headers={
                        "X-Access-Token": connection.access_token,
                        "Content-Type": "application/json",
                    },
                )
        except Exception as exc:
            db.rollback()
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                order.hubrise_sync_status = "failed"
                order.hubrise_last_error = f"HubRise order patch error: {exc}"[:255]
                db.commit()
            print(f"[hubrise] order patch failed for order {order_id}: {exc}")
            return

        try:
            response_data = response.json() if response.content else {}
        except ValueError:
            response_data = {"raw_response": response.text}

        print(
            "[hubrise] patch response received",
            {
                "order_id": order_id,
                "status_code": response.status_code,
                "response": response_data,
            },
        )

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            db.rollback()
            return

        if response.is_success:
            order.hubrise_sync_status = "sent"
            order.hubrise_last_error = None
            order.hubrise_synced_at = datetime.now(timezone.utc)
        else:
            order.hubrise_sync_status = "failed"
            order.hubrise_last_error = (
                response_data.get("message") or response.text or "HubRise order patch failed"
            )[:255]
        db.commit()
    finally:
        db.close()


def _build_test_customer(order_type: str) -> dict:
    customer = {
        "first_name": "Jean",
        "last_name": "Dupont",
        "phone": "0601020304",
    }
    if order_type == "delivery":
        customer.update(
            {
                "address_1": "10 Rue de la Paix",
                "postal_code": "75002",
                "city": "Paris",
                "country": "FR",
            }
        )
    return customer


def build_hubrise_test_order_payload(db: Session, restaurant_id: int, data: HubriseTestOrderRequest) -> tuple[HubriseConnection, dict]:
    connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == restaurant_id).first()
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HubRise connection not found for this restaurant")

    quantity = max(1, data.quantity)
    items: list[dict] = []
    total_amount = 0.0

    if data.item_kind == "product":
        product = (
            db.query(Product)
            .filter(
                Product.restaurant_id == restaurant_id,
                Product.is_deleted.is_(False),
                Product.is_available.is_(True),
                Product.available_online.is_(True),
            )
            .order_by(Product.id.asc())
            .first()
        )
        if not product:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No available online product found for this restaurant")

        unit_price = float(product.price)
        total_amount = unit_price * quantity
        items.append(
            {
                "private_ref": f"test-product-{product.id}",
                "product_name": product.name,
                "price": _money(unit_price),
                "quantity": str(quantity),
            }
        )
    else:
        menu = (
            db.query(Menu)
            .options(joinedload(Menu.categories).joinedload(MenuCategory.options))
            .filter(
                Menu.restaurant_id == restaurant_id,
                Menu.is_available.is_(True),
                Menu.available_online.is_(True),
            )
            .order_by(Menu.id.asc())
            .first()
        )
        if not menu:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No available online menu found for this restaurant")

        selected_options: list[dict] = []
        option_total = 0.0
        flat_options: list[MenuOption] = []
        for category in menu.categories:
            flat_options.extend(category.options)

        if data.include_paid_option:
            paid_option = next((option for option in flat_options if float(option.additional_price) > 0), None)
            if paid_option:
                selected_options.append(
                    {
                        "option_list_name": "Customization",
                        "name": paid_option.name,
                        "price": _money(float(paid_option.additional_price)),
                        "quantity": 1,
                    }
                )
                option_total += float(paid_option.additional_price)

        if data.include_free_option:
            free_option = next((option for option in flat_options if float(option.additional_price) == 0), None)
            if free_option:
                if not any(option["name"] == free_option.name for option in selected_options):
                    selected_options.append(
                        {
                            "option_list_name": "Customization",
                            "name": free_option.name,
                            "price": _money(float(free_option.additional_price)),
                            "quantity": 1,
                        }
                    )

        unit_price = float(menu.price) + option_total
        total_amount = unit_price * quantity
        item_payload = {
            "private_ref": f"test-menu-{menu.id}",
            "product_name": menu.name,
            "price": _money(float(menu.price)),
            "quantity": str(quantity),
        }
        if selected_options:
            item_payload["options"] = selected_options
        items.append(item_payload)
        total_amount = (
            float(menu.price) * quantity
            + sum(float(option["price"].split()[0]) * quantity for option in selected_options)
        )

    test_ref_suffix = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "channel": "yumco-test",
        "ref": f"TEST-{restaurant_id}-{test_ref_suffix}",
        "private_ref": f"test-{restaurant_id}-{data.item_kind}-{data.order_type}-{test_ref_suffix}",
        "status": "new",
        "service_type": _service_type(data.order_type),
        "asap": True,
        "items": items,
        "seller_notes": "Commande de test HubRise envoyee par Yumco.",
        "customer": _build_test_customer(data.order_type),
    }
    if data.order_type == "delivery":
        payload["seller_notes"] += " Livraison de test."
    else:
        payload["seller_notes"] += " Retrait sur place de test."

    if data.is_paid:
        payload["payments"] = [
            {
                "name": "Yumco",
                "ref": "YUMCO-TEST",
                "amount": _money(total_amount),
                "info": {"payment_status": "paid", "test": True},
            }
        ]
        payload["seller_notes"] += " Commande deja payee."
    else:
        payload["seller_notes"] += " Paiement a encaisser sur place."

    return connection, payload


async def send_hubrise_test_order(db: Session, restaurant_id: int, data: HubriseTestOrderRequest) -> tuple[dict, dict]:
    connection, payload = build_hubrise_test_order_payload(db, restaurant_id, data)
    status_code, response_data = await _post_hubrise_order(connection, payload)
    print(
        "[hubrise] test order response",
        {
            "restaurant_id": restaurant_id,
            "status_code": status_code,
            "payload": payload,
            "response": response_data,
        },
    )
    if not 200 <= status_code < 300:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "HubRise test order failed",
                "status_code": status_code,
                "response": response_data,
            },
        )
    return payload, response_data
