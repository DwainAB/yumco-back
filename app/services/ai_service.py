import json
from datetime import datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.category import Category
from app.models.product import Product
from app.models.restaurant import Restaurant
from app.schemas.ai import AIChatMessage, AIChatRequest, AIChatResponse, AIUsageInfo
from app.services.ai_conversation_service import add_ai_conversation_message, get_ai_conversation
from app.services.customer_analytics_service import get_customer_analytics
from app.services.order_analytics_service import get_order_analytics
from app.services.performance_analytics_service import get_performance_analytics
from app.services.revenue_analytics_service import get_revenue_analytics
from app.services.subscription_service import (
    MAX_OUTPUT_TOKENS_PER_REQUEST,
    consume_ai_quota,
    ensure_ai_request_within_limits,
    estimate_text_tokens,
    get_subscription_usage,
)


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
HTTP_TIMEOUT_SECONDS = 45.0


SOUTHERN_HEMISPHERE_COUNTRIES = {
    "australia",
    "new zealand",
    "argentina",
    "chile",
    "south africa",
    "uruguay",
    "paraguay",
    "bolivia",
    "brazil",
}


def _season_hint(country: str | None, now: datetime) -> str | None:
    if not country:
        return None

    month = now.month
    country_normalized = country.strip().lower()
    is_southern = country_normalized in SOUTHERN_HEMISPHERE_COUNTRIES

    if month in {12, 1, 2}:
        return "summer" if is_southern else "winter"
    if month in {3, 4, 5}:
        return "autumn" if is_southern else "spring"
    if month in {6, 7, 8}:
        return "winter" if is_southern else "summer"
    return "spring" if is_southern else "autumn"


def _serialize_history(history: list[AIChatMessage]) -> list[dict[str, str]]:
    serialized = []
    for message in history[-8:]:
        role = message.role.strip().lower()
        if role not in {"user", "assistant"}:
            continue
        serialized.append({"role": role, "content": message.content.strip()})
    return serialized


def _build_catalog_context(db: Session, restaurant_id: int) -> dict:
    rows = (
        db.query(
            Category.name.label("category_name"),
            Category.kind.label("category_kind"),
            Product.name.label("product_name"),
            Product.price.label("product_price"),
        )
        .join(Product, Product.category_id == Category.id)
        .filter(
            Category.restaurant_id == restaurant_id,
            Product.restaurant_id == restaurant_id,
            Product.is_deleted.is_(False),
            Product.is_available.is_(True),
        )
        .order_by(Category.name.asc(), Product.name.asc())
        .all()
    )

    grouped: dict[str, dict] = {}
    for row in rows:
        bucket = grouped.setdefault(
            row.category_name,
            {
                "kind": row.category_kind,
                "products": [],
            },
        )
        if len(bucket["products"]) >= 8:
            continue
        bucket["products"].append(
            {
                "name": row.product_name,
                "price": float(row.product_price),
            }
        )

    catalog = []
    for category_name, data in grouped.items():
        catalog.append(
            {
                "category_name": category_name,
                "kind": data["kind"],
                "products": data["products"],
            }
        )
        if len(catalog) >= 12:
            break
    return {"categories": catalog}


def _build_restaurant_context(db: Session, restaurant: Restaurant) -> dict:
    now = datetime.now()
    address = restaurant.address
    return {
        "restaurant": {
            "id": restaurant.id,
            "name": restaurant.name,
            "timezone": restaurant.timezone,
            "city": address.city if address else None,
            "country": address.country if address else None,
            "postal_code": address.postal_code if address else None,
            "season_hint": _season_hint(address.country if address else None, now),
            "current_month": now.strftime("%B"),
        },
        "catalog": _build_catalog_context(db, restaurant.id),
        "analytics": {
            "revenue": get_revenue_analytics(db, restaurant.id),
            "orders": get_order_analytics(db, restaurant.id),
            "customers": get_customer_analytics(db, restaurant.id),
            "performance": get_performance_analytics(db, restaurant.id),
        },
    }


def _build_system_prompt() -> str:
    return (
        "Tu es l'assistant strategique d'un restaurateur.\n"
        "Tu reponds uniquement dans le cadre du restaurant fourni.\n"
        "Tu t'appuies en priorite sur les analytics, le catalogue et le contexte du restaurant.\n"
        "Tu peux proposer des idees de produits, de carte, de saisonnalite ou de localisation, "
        "mais tu dois les presenter comme des recommandations business et non comme des faits certains "
        "si les donnees ne prouvent pas directement le point.\n"
        "Si une question depasse les donnees disponibles, dis-le clairement puis propose des hypotheses utiles.\n"
        "N'invente jamais de chiffres.\n"
        "Reponds dans la langue du client, avec un ton professionnel, concret, fluide et naturel.\n"
        "Va droit au but.\n"
        "N'utilise pas de titres automatiques comme 'Reponse courte', 'Pourquoi' ou 'Action conseillee' sauf si c'est vraiment utile.\n"
        "N'utilise pas de markdown decoratif.\n"
        "N'utilise pas de texte en gras, donc pas de **...**.\n"
        "Ecris comme dans une vraie conversation avec un restaurateur.\n"
    )


def _build_user_input(payload: AIChatRequest, context: dict) -> str:
    history = _serialize_history(payload.history)
    compact_context = json.dumps(context, ensure_ascii=True, default=str)
    compact_history = json.dumps(history, ensure_ascii=True, default=str)
    return (
        f"Question du restaurateur:\n{payload.message.strip()}\n\n"
        f"Historique recent:\n{compact_history}\n\n"
        f"Contexte restaurant:\n{compact_context}"
    )


def _extract_output_text(response_json: dict) -> str:
    output_text = response_json.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    texts: list[str] = []
    for item in response_json.get("output", []):
        for content in item.get("content", []):
            text_value = content.get("text")
            if isinstance(text_value, str) and text_value.strip():
                texts.append(text_value.strip())
    return "\n".join(texts).strip()


def _extract_usage(response_json: dict) -> tuple[int, int, int]:
    usage = response_json.get("usage", {})
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


async def generate_restaurant_ai_response(
    db: Session,
    restaurant: Restaurant,
    payload: AIChatRequest,
) -> AIChatResponse:
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured",
        )

    if payload.conversation_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="conversation_id is required",
        )

    context = _build_restaurant_context(db, restaurant)
    conversation = get_ai_conversation(db, restaurant.id, payload.conversation_id)
    history = [
        AIChatMessage(role=message.role, content=message.content)
        for message in conversation.messages[-8:]
        if message.role in {"user", "assistant"}
    ]

    system_prompt = _build_system_prompt()
    prepared_payload = AIChatRequest(
        conversation_id=payload.conversation_id,
        message=payload.message,
        history=history,
    )
    user_input = _build_user_input(prepared_payload, context)
    estimated_input_tokens = estimate_text_tokens(system_prompt) + estimate_text_tokens(user_input)

    ensure_ai_request_within_limits(
        db,
        restaurant,
        input_tokens=estimated_input_tokens,
        reserved_output_tokens=MAX_OUTPUT_TOKENS_PER_REQUEST,
    )

    body = {
        "model": settings.OPENAI_MODEL,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_input}],
            },
        ],
        "max_output_tokens": MAX_OUTPUT_TOKENS_PER_REQUEST,
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
        )

    if response.status_code >= 400:
        error_detail = None
        try:
            response_json = response.json()
            error_detail = response_json.get("error", {}).get("message")
        except Exception:
            error_detail = response.text.strip() or None
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error_detail or "OpenAI request failed",
        )

    response_json = response.json()
    answer = _extract_output_text(response_json)
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI returned an empty answer",
        )

    input_tokens, output_tokens, total_tokens = _extract_usage(response_json)
    if total_tokens <= 0:
        total_tokens = estimated_input_tokens + MAX_OUTPUT_TOKENS_PER_REQUEST
        input_tokens = estimated_input_tokens
        output_tokens = MAX_OUTPUT_TOKENS_PER_REQUEST

    if conversation is not None:
        add_ai_conversation_message(
            db,
            conversation,
            role="user",
            content=payload.message.strip(),
        )
        add_ai_conversation_message(
            db,
            conversation,
            role="assistant",
            content=answer,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    updated_restaurant = consume_ai_quota(
        db,
        restaurant,
        message_amount=1,
        token_amount=total_tokens,
    )
    usage = get_subscription_usage(db, updated_restaurant)

    return AIChatResponse(
        conversation_id=conversation.id if conversation is not None else 0,
        answer=answer,
        model=settings.OPENAI_MODEL,
        usage=AIUsageInfo(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            remaining_messages=usage["usage_remaining"],
            remaining_tokens=usage["token_usage_remaining"],
        ),
    )
