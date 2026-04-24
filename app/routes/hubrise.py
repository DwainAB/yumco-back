from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.db.database import get_db
from app.models.hubrise_connection import HubriseConnection
from app.models.order import Order
from app.models.role import Role
from app.services.hubrise_service import (
    apply_hubrise_order_update,
    exchange_code_for_tokens,
    parse_restaurant_id_from_state,
    register_hubrise_order_callback,
    save_hubrise_connection,
    verify_hubrise_signature,
)
from app.services.order_email_service import send_order_cancelled, send_order_completed, send_order_preparing
from app.models.restaurant import Restaurant
from app.models.user import User
from app.schemas.restaurant import RestaurantHubriseStatusResponse


router = APIRouter(tags=["hubrise"])


def _build_hubrise_result_url(status_value: str, restaurant_id: int | None = None, message: str | None = None) -> str:
    redirect_uri = settings.HUBRISE_RESULT_REDIRECT_URI
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="HUBRISE_RESULT_REDIRECT_URI must be configured for HubRise redirects",
        )

    params: dict[str, str] = {"status": status_value}
    if restaurant_id is not None:
        params["restaurant_id"] = str(restaurant_id)
    if message:
        params["message"] = message

    separator = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{separator}{urlencode(params)}"


@router.get("/restaurants/{restaurant_id}/hubrise/status", response_model=RestaurantHubriseStatusResponse)
def get_restaurant_hubrise_status(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id, Restaurant.is_deleted.is_(False)).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    has_access = current_user.is_admin or (
        db.query(Role)
        .filter(Role.restaurant_id == restaurant_id, Role.user_id == current_user.id)
        .first()
        is not None
    )
    if not has_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this restaurant")

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


@router.delete("/restaurants/{restaurant_id}/hubrise/connection", status_code=status.HTTP_204_NO_CONTENT)
def delete_restaurant_hubrise_connection(
    restaurant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id, Restaurant.is_deleted.is_(False)).first()
    if not restaurant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    has_access = current_user.is_admin or (
        db.query(Role)
        .filter(Role.restaurant_id == restaurant_id, Role.user_id == current_user.id)
        .first()
        is not None
    )
    if not has_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this restaurant")

    connection = db.query(HubriseConnection).filter(HubriseConnection.restaurant_id == restaurant_id).first()
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HubRise is not connected for this restaurant")

    db.delete(connection)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/integrations/hubrise/callback")
async def hubrise_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    restaurant_id: int | None = None

    try:
        restaurant_id = parse_restaurant_id_from_state(state)

        if not code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code")

        token_data = await exchange_code_for_tokens(code)
        connection = save_hubrise_connection(db, restaurant_id, token_data)
        await register_hubrise_order_callback(connection)
        return RedirectResponse(
            url=_build_hubrise_result_url(
                "success",
                restaurant_id=restaurant_id,
                message="HubRise connection saved",
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except HTTPException as exc:
        db.rollback()
        return RedirectResponse(
            url=_build_hubrise_result_url(
                "error",
                restaurant_id=restaurant_id,
                message=str(exc.detail),
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception:
        db.rollback()
        return RedirectResponse(
            url=_build_hubrise_result_url(
                "error",
                restaurant_id=restaurant_id,
                message="Unexpected HubRise callback error",
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/integrations/hubrise/webhook", status_code=status.HTTP_200_OK)
async def hubrise_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_hubrise_hmac_sha256: str | None = Header(default=None),
):
    raw_body = await request.body()
    if not verify_hubrise_signature(raw_body, x_hubrise_hmac_sha256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid HubRise signature")

    payload = await request.json()
    print("[hubrise] webhook received", payload)
    result = apply_hubrise_order_update(db, payload)
    if result is not None:
        order, previous_status, current_status = result
        if current_status != previous_status:
            restaurant = db.query(Restaurant).filter(Restaurant.id == order.restaurant_id).first()
            if restaurant:
                if current_status == "preparing":
                    await send_order_preparing(order, restaurant)
                elif current_status == "completed":
                    await send_order_completed(order, restaurant)
                elif current_status == "cancelled":
                    await send_order_cancelled(order, restaurant)
    return Response(status_code=status.HTTP_200_OK)
