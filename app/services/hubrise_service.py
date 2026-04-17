import json

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.hubrise_connection import HubriseConnection
from app.models.restaurant import Restaurant

HUBRISE_TOKEN_URL = "https://manager.hubrise.com/oauth2/v1/token"


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
