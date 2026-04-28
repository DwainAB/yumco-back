import httpx
from app.db.database import SessionLocal
from app.models.user import User
from app.models.user_device import UserDevice
from app.models.role import Role
from app.services.user_service import deactivate_push_tokens


EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_expo_push(tokens: list[str], title: str, body: str, data: dict = None):
    if not tokens:
        return

    messages = []
    for token_info in tokens:
        if isinstance(token_info, str):
            token = token_info
            platform = None
        else:
            token = token_info.get("expo_push_token")
            platform = (token_info.get("platform") or "").lower()

        if not token or not token.startswith("ExponentPushToken"):
            continue

        message = {
            "to": token,
            "sound": "sound_notif.wav",
            "title": title,
            "body": body,
            **({"data": data} if data else {}),
        }
        if platform == "android":
            message["channelId"] = "orders_v2"
        messages.append(message)

    if not messages:
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as e:
        print(f"[notification_service] Erreur envoi push: {e}")
        return

    invalid_tokens: list[str] = []
    for message, ticket in zip(messages, payload.get("data", [])):
        details = ticket.get("details") or {}
        if ticket.get("status") == "error" and details.get("error") == "DeviceNotRegistered":
            invalid_tokens.append(message["to"])

    if invalid_tokens:
        db = SessionLocal()
        try:
            deactivate_push_tokens(db, invalid_tokens)
        finally:
            db.close()


async def notify_new_reservation(restaurant_id: int, full_name: str, number_of_people: int, reservation_date: str, reservation_time: str):
    db = SessionLocal()
    try:
        devices = (
            db.query(UserDevice)
            .join(User, User.id == UserDevice.user_id)
            .join(Role, Role.user_id == User.id)
            .filter(
                Role.restaurant_id == restaurant_id,
                Role.type.in_(["owner", "manager", "staff"]),
                UserDevice.is_active == True,
                User.notify_reservations == True,
            )
            .all()
        )
        tokens = [
            {
                "expo_push_token": device.expo_push_token,
                "platform": device.platform,
            }
            for device in devices
        ]
    finally:
        db.close()

    await send_expo_push(
        tokens=tokens,
        title="Nouvelle réservation !",
        body=f"{full_name} — {number_of_people} pers. le {reservation_date} à {reservation_time}",
        data={"type": "new_reservation", "restaurant_id": restaurant_id},
    )


async def notify_new_order(restaurant_id: int, order_number: str):
    db = SessionLocal()
    try:
        devices = (
            db.query(UserDevice)
            .join(User, User.id == UserDevice.user_id)
            .join(Role, Role.user_id == User.id)
            .filter(
                Role.restaurant_id == restaurant_id,
                Role.type.in_(["owner", "manager", "staff"]),
                UserDevice.is_active == True,
                User.notify_orders == True,
            )
            .all()
        )
        tokens = [
            {
                "expo_push_token": device.expo_push_token,
                "platform": device.platform,
            }
            for device in devices
        ]
    finally:
        db.close()

    await send_expo_push(
        tokens=tokens,
        title="Nouvelle commande !",
        body=f"La commande {order_number} vient d'être passée.",
        data={"type": "new_order", "restaurant_id": restaurant_id},
    )
