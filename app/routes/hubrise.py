from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.services.hubrise_service import exchange_code_for_tokens, parse_restaurant_id_from_state, save_hubrise_connection


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
        save_hubrise_connection(db, restaurant_id, token_data)
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
