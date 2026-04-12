from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.restaurant import Restaurant


PLAN_LIMITS = {
    "starter": 0,
    "pro_ai": 150,
    "business_ai": 500,
}

PLAN_TOKEN_LIMITS = {
    "starter": 0,
    "pro_ai": 300_000,
    "business_ai": 1_000_000,
}

MAX_INPUT_TOKENS_PER_REQUEST = 8_000
MAX_OUTPUT_TOKENS_PER_REQUEST = 1_200

PLAN_UPGRADE_MESSAGES = {
    "starter": "Passez a l'offre Pro IA pour activer l'assistant IA.",
    "pro_ai": "Vous avez atteint votre quota IA mensuel. Passez a l'offre Business IA ou attendez le prochain cycle mensuel.",
    "business_ai": "Vous avez atteint votre quota IA mensuel. Attendez le prochain cycle mensuel.",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_plan(plan: str) -> str:
    normalized_plan = plan.strip().lower()
    if normalized_plan not in PLAN_LIMITS:
        raise ValueError(f"subscription_plan must be one of: {', '.join(sorted(PLAN_LIMITS))}")
    return normalized_plan


def _next_cycle_start(cycle_started_at: datetime) -> datetime:
    return cycle_started_at + timedelta(days=30)


def ensure_ai_cycle_is_current(db: Session, restaurant: Restaurant) -> Restaurant:
    if restaurant.ai_cycle_started_at is None:
        restaurant.ai_cycle_started_at = _utcnow()
        restaurant.ai_usage_count = 0
        restaurant.ai_token_usage_count = 0
        db.commit()
        db.refresh(restaurant)
        return restaurant

    next_cycle = _next_cycle_start(restaurant.ai_cycle_started_at)
    if _utcnow() >= next_cycle:
        restaurant.ai_cycle_started_at = _utcnow()
        restaurant.ai_usage_count = 0
        restaurant.ai_token_usage_count = 0
        db.commit()
        db.refresh(restaurant)

    return restaurant


def apply_subscription_plan(db: Session, restaurant: Restaurant, subscription_plan: str, cycle_started_at: datetime | None = None) -> Restaurant:
    normalized_plan = _normalize_plan(subscription_plan)
    previous_plan = restaurant.subscription_plan

    restaurant.subscription_plan = normalized_plan
    restaurant.ai_monthly_quota = PLAN_LIMITS[normalized_plan]
    restaurant.ai_monthly_token_quota = PLAN_TOKEN_LIMITS[normalized_plan]

    if cycle_started_at is not None:
        restaurant.ai_cycle_started_at = cycle_started_at
        restaurant.ai_usage_count = 0
        restaurant.ai_token_usage_count = 0
    elif previous_plan != normalized_plan:
        restaurant.ai_cycle_started_at = _utcnow()
        restaurant.ai_usage_count = 0
        restaurant.ai_token_usage_count = 0
    elif restaurant.ai_cycle_started_at is None:
        restaurant.ai_cycle_started_at = _utcnow()

    db.commit()
    db.refresh(restaurant)
    return restaurant


def get_subscription_usage(db: Session, restaurant: Restaurant) -> dict:
    restaurant = ensure_ai_cycle_is_current(db, restaurant)
    usage_remaining = max(restaurant.ai_monthly_quota - restaurant.ai_usage_count, 0)
    token_usage_remaining = max(restaurant.ai_monthly_token_quota - restaurant.ai_token_usage_count, 0)
    cycle_ends_at = _next_cycle_start(restaurant.ai_cycle_started_at) if restaurant.ai_cycle_started_at else None
    is_ai_enabled = restaurant.ai_monthly_quota > 0
    is_quota_reached = is_ai_enabled and usage_remaining <= 0
    is_token_quota_reached = is_ai_enabled and token_usage_remaining <= 0

    return {
        "plan": restaurant.subscription_plan,
        "interval": getattr(restaurant, "subscription_interval", "month"),
        "subscription_status": getattr(restaurant, "subscription_status", None),
        "subscription_cancel_at_period_end": bool(getattr(restaurant, "subscription_cancel_at_period_end", False)),
        "subscription_current_period_ends_at": getattr(restaurant, "subscription_current_period_ends_at", None),
        "has_tablet_rental": bool(getattr(restaurant, "has_tablet_rental", False)),
        "has_printer_rental": bool(getattr(restaurant, "has_printer_rental", False)),
        "monthly_quota": restaurant.ai_monthly_quota,
        "usage_count": restaurant.ai_usage_count,
        "usage_remaining": usage_remaining,
        "monthly_token_quota": restaurant.ai_monthly_token_quota,
        "token_usage_count": restaurant.ai_token_usage_count,
        "token_usage_remaining": token_usage_remaining,
        "cycle_started_at": restaurant.ai_cycle_started_at,
        "cycle_ends_at": cycle_ends_at,
        "is_ai_enabled": is_ai_enabled,
        "is_quota_reached": is_quota_reached,
        "is_token_quota_reached": is_token_quota_reached,
        "upgrade_message": PLAN_UPGRADE_MESSAGES.get(restaurant.subscription_plan) if (not is_ai_enabled or is_quota_reached or is_token_quota_reached) else None,
    }


def estimate_text_tokens(text: str) -> int:
    normalized_text = text.strip()
    if not normalized_text:
        return 0
    return max(1, (len(normalized_text) + 3) // 4)


def ensure_ai_request_within_limits(
    db: Session,
    restaurant: Restaurant,
    input_tokens: int,
    reserved_output_tokens: int = MAX_OUTPUT_TOKENS_PER_REQUEST,
) -> Restaurant:
    restaurant = ensure_ai_cycle_is_current(db, restaurant)
    if restaurant.ai_monthly_quota <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PLAN_UPGRADE_MESSAGES["starter"],
        )

    if restaurant.ai_usage_count + 1 > restaurant.ai_monthly_quota:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PLAN_UPGRADE_MESSAGES.get(restaurant.subscription_plan, PLAN_UPGRADE_MESSAGES["business_ai"]),
        )

    if input_tokens > MAX_INPUT_TOKENS_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Votre question est trop longue. Reduisez le message avant de reessayer.",
        )

    estimated_total_tokens = input_tokens + reserved_output_tokens
    if restaurant.ai_token_usage_count + estimated_total_tokens > restaurant.ai_monthly_token_quota:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PLAN_UPGRADE_MESSAGES.get(restaurant.subscription_plan, PLAN_UPGRADE_MESSAGES["business_ai"]),
        )

    return restaurant


def consume_ai_quota(db: Session, restaurant: Restaurant, message_amount: int = 1, token_amount: int = 0) -> Restaurant:
    restaurant = ensure_ai_cycle_is_current(db, restaurant)
    if restaurant.ai_monthly_quota <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PLAN_UPGRADE_MESSAGES["starter"],
        )

    if restaurant.ai_usage_count + message_amount > restaurant.ai_monthly_quota:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PLAN_UPGRADE_MESSAGES.get(restaurant.subscription_plan, PLAN_UPGRADE_MESSAGES["business_ai"]),
        )

    if restaurant.ai_token_usage_count + token_amount > restaurant.ai_monthly_token_quota:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PLAN_UPGRADE_MESSAGES.get(restaurant.subscription_plan, PLAN_UPGRADE_MESSAGES["business_ai"]),
        )

    restaurant.ai_usage_count += message_amount
    restaurant.ai_token_usage_count += token_amount
    db.commit()
    db.refresh(restaurant)
    return restaurant
