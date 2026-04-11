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


REASON_CONTENT = {
    "missing_starter": {
        "title": "Ajoute une entree",
        "message": "Cette entree complete bien les plats deja ajoutes au panier.",
    },
    "missing_drink": {
        "title": "Ajoute une boisson",
        "message": "Une boisson est souvent ajoutee avec ce type de commande.",
    },
    "missing_side": {
        "title": "Ajoute un accompagnement",
        "message": "Un accompagnement peut completer ce plat principal.",
    },
    "missing_dessert": {
        "title": "Ajoute un dessert",
        "message": "Un dessert est une bonne suggestion pour completer la commande.",
    },
    "frequently_bought_together": {
        "title": "Souvent commande avec ce panier",
        "message": "Ce produit est souvent achete avec les articles deja selectionnes.",
    },
    "popular_in_restaurant": {
        "title": "Produit populaire",
        "message": "Ce produit est souvent choisi par les clients du restaurant.",
    },
}


MAX_STARTER_SUGGESTION_MAIN_COUNT = 2
MAX_DESSERT_SUGGESTION_MAIN_COUNT = 3
MAX_TOTAL_ITEMS_FOR_EXTRA_SUGGESTIONS = 6


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


def _should_exclude_candidate(
    candidate_category_type: str | None,
    category_quantities: dict[str, int],
    total_items_count: int,
) -> bool:
    main_count = category_quantities.get("main", 0)
    starter_count = category_quantities.get("starter", 0)
    side_count = category_quantities.get("side", 0)
    dessert_count = category_quantities.get("dessert", 0)

    if candidate_category_type == "starter":
        if starter_count >= 1:
            return True
        if main_count > MAX_STARTER_SUGGESTION_MAIN_COUNT:
            return True
        if total_items_count >= MAX_TOTAL_ITEMS_FOR_EXTRA_SUGGESTIONS:
            return True

    if candidate_category_type == "dessert":
        if dessert_count >= 1:
            return True
        if main_count > MAX_DESSERT_SUGGESTION_MAIN_COUNT:
            return True
        if total_items_count >= MAX_TOTAL_ITEMS_FOR_EXTRA_SUGGESTIONS:
            return True

    if candidate_category_type == "side" and side_count >= main_count and main_count > 0:
        return True

    if candidate_category_type == "drink" and category_quantities.get("drink", 0) >= main_count and main_count > 0:
        return True

    return False


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


def _get_product_order_counts(db: Session, restaurant_id: int, product_ids: list[int]) -> dict[int, int]:
    if not product_ids:
        return {}

    rows = (
        db.query(OrderItem.product_id, func.count(func.distinct(OrderItem.order_id)).label("count"))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != "cancelled",
            OrderItem.parent_order_item_id.is_(None),
            OrderItem.product_id.in_(product_ids),
        )
        .group_by(OrderItem.product_id)
        .all()
    )
    return {product_id: count for product_id, count in rows if product_id is not None}


def _get_copurchase_strengths(db: Session, restaurant_id: int, basket_product_ids: list[int]) -> dict[int, float]:
    if not basket_product_ids:
        return {}

    basket_order_counts = _get_product_order_counts(db, restaurant_id, basket_product_ids)
    rows = (
        db.query(
            OrderItem.product_id.label("basket_product_id"),
            OrderItem.order_id.label("order_id"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.restaurant_id == restaurant_id,
            OrderItem.product_id.isnot(None),
            OrderItem.parent_order_item_id.is_(None),
            OrderItem.product_id.in_(basket_product_ids),
        )
        .all()
    )
    basket_orders_map = defaultdict(set)
    for basket_product_id, order_id in rows:
        basket_orders_map[basket_product_id].add(order_id)

    all_matching_order_ids = {
        order_id
        for order_ids in basket_orders_map.values()
        for order_id in order_ids
    }
    if not all_matching_order_ids:
        return {}

    candidate_rows = (
        db.query(OrderItem.order_id, OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.restaurant_id == restaurant_id,
            OrderItem.parent_order_item_id.is_(None),
            OrderItem.product_id.isnot(None),
            OrderItem.order_id.in_(all_matching_order_ids),
            ~OrderItem.product_id.in_(basket_product_ids),
        )
        .all()
    )

    order_candidates_map = defaultdict(set)
    for order_id, product_id in candidate_rows:
        order_candidates_map[order_id].add(product_id)

    candidate_scores = defaultdict(float)
    for basket_product_id, order_ids in basket_orders_map.items():
        basket_order_count = basket_order_counts.get(basket_product_id, 0)
        if basket_order_count == 0:
            continue

        candidate_occurrences = defaultdict(int)
        for order_id in order_ids:
            for candidate_product_id in order_candidates_map.get(order_id, set()):
                candidate_occurrences[candidate_product_id] += 1

        for candidate_product_id, occurrence_count in candidate_occurrences.items():
            candidate_scores[candidate_product_id] += occurrence_count / basket_order_count

    basket_size = len(basket_product_ids)
    if basket_size == 0:
        return {}

    return {
        candidate_product_id: score / basket_size
        for candidate_product_id, score in candidate_scores.items()
    }


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
    total_items_count = sum(basket_quantities.values())

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
    copurchase_strengths = _get_copurchase_strengths(db, restaurant_id, basket_product_ids)
    max_popularity = max(popularity_counts.values(), default=0)
    max_copurchase_strength = max(copurchase_strengths.values(), default=0.0)

    scored_candidates = []
    for candidate in candidate_rows:
        score = 0.0
        reasons: list[tuple[str, float]] = []
        category_type = candidate.category_kind

        if _should_exclude_candidate(category_type, category_quantities, total_items_count):
            continue

        for missing_category_type, reason, weight in missing_category_reasons:
            if category_type == missing_category_type:
                score += weight
                reasons.append((reason, weight))

        copurchase_strength = copurchase_strengths.get(candidate.id, 0.0)
        if max_copurchase_strength and copurchase_strength:
            weight = 0.35 * (copurchase_strength / max_copurchase_strength)
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
        reason_content = REASON_CONTENT[primary_reason]
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
                title=reason_content["title"],
                message=reason_content["message"],
            )
        )

    scored_candidates.sort(key=lambda product: (-product.score, product.name.lower()))
    return RecommendationResponse(recommendations=scored_candidates[: payload.limit])
