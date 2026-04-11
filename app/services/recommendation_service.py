from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.schemas.recommendation import RecommendedProduct, RecommendationRequest, RecommendationResponse


REASON_LABELS = {
    "missing_starter": "missing_starter",
    "missing_drink": "missing_drink",
    "missing_side": "missing_side",
    "missing_dessert": "missing_dessert",
    "frequently_bought_together": "frequently_bought_together",
    "popular_in_restaurant": "popular_in_restaurant",
}

def _build_missing_category_reasons(present_category_types: set[str]) -> list[tuple[str, str, float]]:
    reasons: list[tuple[str, str, float]] = []

    if "main" in present_category_types and "starter" not in present_category_types:
        reasons.append(("starter", REASON_LABELS["missing_starter"], 0.25))
    if "main" in present_category_types and "drink" not in present_category_types:
        reasons.append(("drink", REASON_LABELS["missing_drink"], 0.45))
    if "main" in present_category_types and "side" not in present_category_types:
        reasons.append(("side", REASON_LABELS["missing_side"], 0.30))
    if "main" in present_category_types and "dessert" not in present_category_types:
        reasons.append(("dessert", REASON_LABELS["missing_dessert"], 0.20))

    return reasons


def _build_quantity_based_reasons(category_quantities: dict[str, int]) -> list[tuple[str, str, float]]:
    reasons: list[tuple[str, str, float]] = []
    main_count = category_quantities.get("main", 0)
    if main_count <= 0:
        return reasons

    starter_count = category_quantities.get("starter", 0)
    if starter_count == 0:
        reasons.append(("starter", REASON_LABELS["missing_starter"], 0.25))

    drink_count = category_quantities.get("drink", 0)
    if drink_count < main_count:
        deficit_ratio = (main_count - drink_count) / main_count
        reasons.append(("drink", REASON_LABELS["missing_drink"], round(0.45 * deficit_ratio, 4)))

    side_count = category_quantities.get("side", 0)
    if side_count < main_count:
        deficit_ratio = (main_count - side_count) / main_count
        reasons.append(("side", REASON_LABELS["missing_side"], round(0.30 * deficit_ratio, 4)))

    dessert_count = category_quantities.get("dessert", 0)
    if dessert_count == 0:
        reasons.append(("dessert", REASON_LABELS["missing_dessert"], 0.20))

    return reasons


def _get_popularity_counts(db: Session, restaurant_id: int) -> dict[int, int]:
    rows = (
        db.query(OrderItem.product_id, func.count(OrderItem.id).label("count"))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != "cancelled",
            OrderItem.product_id.isnot(None),
            OrderItem.parent_order_item_id.is_(None),
        )
        .group_by(OrderItem.product_id)
        .all()
    )
    return {product_id: count for product_id, count in rows if product_id is not None}


def _get_copurchase_counts(db: Session, restaurant_id: int, basket_product_ids: list[int]) -> dict[int, int]:
    if not basket_product_ids:
        return {}

    matching_order_ids = (
        db.query(OrderItem.order_id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != "cancelled",
            OrderItem.product_id.in_(basket_product_ids),
            OrderItem.parent_order_item_id.is_(None),
        )
        .distinct()
        .subquery()
    )

    rows = (
        db.query(OrderItem.product_id, func.count(func.distinct(OrderItem.order_id)).label("count"))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.restaurant_id == restaurant_id,
            OrderItem.order_id.in_(matching_order_ids),
            OrderItem.product_id.isnot(None),
            OrderItem.parent_order_item_id.is_(None),
            ~OrderItem.product_id.in_(basket_product_ids),
        )
        .group_by(OrderItem.product_id)
        .all()
    )
    return {product_id: count for product_id, count in rows if product_id is not None}


def get_product_recommendations(
    db: Session,
    restaurant_id: int,
    payload: RecommendationRequest,
) -> RecommendationResponse:
    basket_quantities = defaultdict(int)
    for item in payload.items:
        basket_quantities[item.product_id] += item.quantity

    basket_product_ids = list(basket_quantities.keys())

    basket_products = (
        db.query(
            Product.id,
            Product.category_id,
            Category.name.label("category_name"),
            Category.kind.label("category_kind"),
        )
        .outerjoin(Category, Category.id == Product.category_id)
        .filter(
            Product.restaurant_id == restaurant_id,
            Product.is_deleted.is_(False),
            Product.id.in_(basket_product_ids),
        )
        .all()
    )

    if len(basket_products) != len(basket_product_ids):
        existing_ids = {product.id for product in basket_products}
        missing_ids = [product_id for product_id in basket_product_ids if product_id not in existing_ids]
        raise ValueError(f"Unknown product ids for restaurant {restaurant_id}: {missing_ids}")

    present_category_types = {
        product.category_kind
        for product in basket_products
        if product.category_kind is not None
    }
    category_quantities = defaultdict(int)
    for product in basket_products:
        if product.category_kind is None:
            continue
        category_quantities[product.category_kind] += basket_quantities.get(product.id, 0)

    missing_category_reasons = _build_quantity_based_reasons(category_quantities)
    if not missing_category_reasons:
        missing_category_reasons = _build_missing_category_reasons(present_category_types)

    candidate_rows = (
        db.query(
            Product.id,
            Product.name,
            Product.price,
            Product.image_url,
            Product.category_id,
            Category.name.label("category_name"),
            Category.kind.label("category_kind"),
        )
        .outerjoin(Category, Category.id == Product.category_id)
        .filter(
            Product.restaurant_id == restaurant_id,
            Product.is_deleted.is_(False),
            Product.is_available.is_(True),
            Product.available_online.is_(True),
            ~Product.id.in_(basket_product_ids),
        )
        .all()
    )

    popularity_counts = _get_popularity_counts(db, restaurant_id)
    copurchase_counts = _get_copurchase_counts(db, restaurant_id, basket_product_ids)
    max_popularity = max(popularity_counts.values(), default=0)
    max_copurchase = max(copurchase_counts.values(), default=0)

    scored_candidates = []
    for candidate in candidate_rows:
        score = 0.0
        reasons: list[tuple[str, float]] = []
        category_type = candidate.category_kind

        for missing_category_type, reason, weight in missing_category_reasons:
            if category_type == missing_category_type:
                score += weight
                reasons.append((reason, weight))

        copurchase_count = copurchase_counts.get(candidate.id, 0)
        if max_copurchase and copurchase_count:
            weight = 0.35 * (copurchase_count / max_copurchase)
            score += weight
            reasons.append((REASON_LABELS["frequently_bought_together"], weight))

        popularity_count = popularity_counts.get(candidate.id, 0)
        if max_popularity and popularity_count:
            weight = 0.20 * (popularity_count / max_popularity)
            score += weight
            reasons.append((REASON_LABELS["popular_in_restaurant"], weight))

        if score <= 0:
            continue

        primary_reason = max(reasons, key=lambda item: item[1])[0]
        scored_candidates.append(
            RecommendedProduct(
                product_id=candidate.id,
                name=candidate.name,
                price=candidate.price,
                image_url=candidate.image_url,
                category_id=candidate.category_id,
                category_name=candidate.category_name,
                score=round(score, 4),
                reason=primary_reason,
            )
        )

    scored_candidates.sort(key=lambda product: (-product.score, product.name.lower()))
    return RecommendationResponse(recommendations=scored_candidates[: payload.limit])
