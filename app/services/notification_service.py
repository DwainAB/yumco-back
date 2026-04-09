import httpx
from app.db.database import SessionLocal
from app.models.user import User
from app.models.role import Role


EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_expo_push(tokens: list[str], title: str, body: str, data: dict = None):
    if not tokens:
        return

    messages = [
        {
            "to": token,
            "sound": "default",
            "title": title,
            "body": body,
            **({"data": data} if data else {}),
        }
        for token in tokens
        if token and token.startswith("ExponentPushToken")
    ]

    if not messages:
        return

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
    except Exception as e:
        print(f"[notification_service] Erreur envoi push: {e}")


async def notify_new_order(restaurant_id: int, order_number: str):
    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .join(Role, Role.user_id == User.id)
            .filter(
                Role.restaurant_id == restaurant_id,
                Role.type.in_(["owner", "manager", "staff"]),
                User.expo_push_token.isnot(None),
            )
            .all()
        )
        tokens = [u.expo_push_token for u in users if u.expo_push_token]
    finally:
        db.close()

    await send_expo_push(
        tokens=tokens,
        title="Nouvelle commande !",
        body=f"La commande {order_number} vient d'être passée.",
        data={"type": "new_order", "restaurant_id": restaurant_id},
    )
