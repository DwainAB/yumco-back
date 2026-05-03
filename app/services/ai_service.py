import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

FRENCH_COASTAL_DEPARTMENTS = {
    "06": "mediterranean",
    "11": "mediterranean",
    "13": "mediterranean",
    "17": "atlantic",
    "22": "channel_atlantic",
    "29": "atlantic",
    "2A": "mediterranean",
    "2B": "mediterranean",
    "30": "mediterranean",
    "33": "atlantic",
    "34": "mediterranean",
    "35": "channel_atlantic",
    "40": "atlantic",
    "44": "atlantic",
    "50": "channel",
    "56": "atlantic",
    "59": "channel",
    "62": "channel",
    "64": "atlantic",
    "66": "mediterranean",
    "76": "channel",
    "80": "channel",
    "83": "mediterranean",
    "85": "atlantic",
}

FRENCH_MOUNTAIN_DEPARTMENTS = {
    "01", "04", "05", "06", "09", "15", "25", "26", "31", "38", "39", "42", "43",
    "48", "63", "64", "65", "66", "67", "68", "73", "74", "88", "90",
}

STYLE_KEYWORDS = {
    "asiatique": {
        "nouille", "nouilles", "nems", "riz", "wok", "sushi", "maki", "ramen", "pho", "crevette", "saumon",
        "tempura", "gyoza", "bo bun", "bo-bun", "thaï", "thai", "curry", "yakitori", "bao", "dim sum",
    },
    "italien": {
        "pizza", "pasta", "pates", "pâtes", "risotto", "gnocchi", "lasagne", "carbo", "carbonara", "mozza",
        "parmesan", "tiramisu", "focaccia",
    },
    "burger": {
        "burger", "cheeseburger", "bacon", "fries", "frites", "smash", "tenders", "nuggets",
    },
    "grill": {
        "grill", "entrecote", "entrecôte", "brochette", "cote", "côte", "barbecue", "bbq", "steak", "poulet roti",
    },
    "boulangerie_patisserie": {
        "croissant", "pain", "baguette", "viennoiserie", "tarte", "eclair", "éclair", "patisserie", "pâtisserie",
        "flan", "millefeuille",
    },
    "cafe_brunch": {
        "brunch", "cafe", "café", "latte", "cappuccino", "avocado", "toast", "pancake", "granola", "oeufs", "œufs",
    },
    "mediterraneen": {
        "mezze", "houmous", "hummus", "falafel", "shawarma", "kebab", "taboule", "taboulé", "grillade", "couscous",
    },
}

WEB_SEARCH_TRIGGER_PATTERNS = (
    r"\bmodifier\b.*\b(carte|menu)\b",
    r"\bchanger\b.*\b(carte|menu)\b",
    r"\bajout(?:er|e|ons)?\b.*\b(produit|plat|dessert|boisson|entree|entrée|menu|carte)\b",
    r"\bnouveau\b.*\b(produit|plat|dessert|boisson|menu)\b",
    r"\blancer\b.*\b(produit|plat|dessert|boisson|menu)\b",
    r"\bquel\b.*\b(dessert|boisson|plat|produit)\b.*\b(lancer|ajouter)\b",
    r"\bqu[ea] ?peut[- ]?on ajouter\b.*\b(carte|menu)?\b",
    r"\btendance(?:s)?\b",
    r"\bactuel(?:le|les)?\b",
    r"\ben ce moment\b",
    r"\bsaisonn(?:ier|iere|iers|ieres|alité|alite)\b",
    r"\bfournisseur(?:s)?\b",
    r"\bgrossiste(?:s)?\b",
    r"\bdans le coin\b",
    r"\b[aà] proximit[eé]\b",
    r"\bconcurren(?:ce|ts?)\b",
    r"\bautour de nous\b",
)

WEB_SEARCH_CACHE_TTL_SECONDS = 6 * 60 * 60
SEARCH_TOPIC_STOPWORDS = {
    "a", "au", "aux", "avec", "ce", "ces", "coherent", "coherente", "cohérent", "cohérente",
    "comment", "dans", "de", "des", "du", "en", "est", "et", "faut", "il", "la", "le", "les",
    "lancer", "leur", "local", "locale", "locales", "locaux", "ma", "mes", "modifier", "mon",
    "notre", "nos", "ou", "par", "peut", "plus", "pour", "produit", "produits", "proximite",
    "proximité", "quel", "quelle", "quelles", "quels", "que", "restaurant", "sa", "ses", "sur",
    "tendance", "tendances", "un", "une", "vendre", "vers", "voici", "carte", "menu",
}

WEB_SEARCH_RESPONSE_CACHE: dict[str, dict] = {}


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


def _get_local_now(timezone_name: str | None) -> datetime:
    if timezone_name:
        try:
            return datetime.now(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            pass
    return datetime.now()


def _normalize_text_for_matching(value: str) -> str:
    return value.strip().lower()


def _infer_style_profile(category_names: list[str], product_names: list[str]) -> dict:
    corpus = " ".join(category_names + product_names).lower()
    matches: list[dict[str, int | str]] = []
    for style, keywords in STYLE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in corpus)
        if score > 0:
            matches.append({"style": style, "score": score})

    matches.sort(key=lambda item: int(item["score"]), reverse=True)
    primary_style = str(matches[0]["style"]) if matches else "generaliste"
    return {
        "primary_style": primary_style,
        "matched_styles": matches[:3],
    }


def _normalize_country(country: str | None) -> str | None:
    return country.strip().lower() if country else None


def _to_iso_country_code(country: str | None) -> str | None:
    normalized_country = _normalize_country(country)
    if not normalized_country:
        return None

    country_aliases = {
        "fr": "FR",
        "france": "FR",
        "be": "BE",
        "belgique": "BE",
        "belgium": "BE",
        "es": "ES",
        "espagne": "ES",
        "spain": "ES",
        "it": "IT",
        "italie": "IT",
        "italy": "IT",
        "de": "DE",
        "allemagne": "DE",
        "germany": "DE",
        "pt": "PT",
        "portugal": "PT",
        "uk": "GB",
        "gb": "GB",
        "royaume-uni": "GB",
        "united kingdom": "GB",
        "us": "US",
        "usa": "US",
        "united states": "US",
        "etats-unis": "US",
    }
    return country_aliases.get(normalized_country)


def _extract_department_code(postal_code: str | None, country: str | None) -> str | None:
    if not postal_code:
        return None

    normalized_country = _normalize_country(country)
    compact = postal_code.replace(" ", "").upper()
    if normalized_country not in {"fr", "france"}:
        return compact[:3] if len(compact) >= 3 else compact

    if compact.startswith(("2A", "2B")):
        return compact[:2]
    if len(compact) >= 2:
        return compact[:2]
    return compact


def _infer_geographic_profile(address: object | None) -> dict:
    if not address:
        return {
            "country_normalized": None,
            "department_code": None,
            "is_coastal_likely": False,
            "coast_type": None,
            "is_mountain_area_likely": False,
            "location_profile": "unknown",
            "local_product_biases": [],
        }

    country = str(getattr(address, "country", "") or "").strip()
    city = str(getattr(address, "city", "") or "").strip()
    postal_code = str(getattr(address, "postal_code", "") or "").strip()
    normalized_country = _normalize_country(country)
    department_code = _extract_department_code(postal_code, country)

    is_coastal_likely = False
    coast_type = None
    is_mountain_area_likely = False
    local_product_biases: list[str] = []

    if normalized_country in {"fr", "france"} and department_code:
        coast_type = FRENCH_COASTAL_DEPARTMENTS.get(department_code)
        is_coastal_likely = coast_type is not None
        is_mountain_area_likely = department_code in FRENCH_MOUNTAIN_DEPARTMENTS

    if is_coastal_likely:
        location_profile = "coastal"
        local_product_biases.extend(
            [
                "seafood can be more credible if it already fits the menu style",
                "fresh fish suggestions are more plausible when aligned with the existing offer",
            ]
        )
    elif is_mountain_area_likely:
        location_profile = "mountain"
        local_product_biases.extend(
            [
                "comfort food and seasonal hearty dishes can be more credible if they fit the menu",
                "regional sourcing logic may lean toward local meats, cheeses or mountain produce",
            ]
        )
    else:
        location_profile = "inland"

    if city:
        local_product_biases.append(f"city context: {city}")

    return {
        "country_normalized": normalized_country,
        "department_code": department_code,
        "is_coastal_likely": is_coastal_likely,
        "coast_type": coast_type,
        "is_mountain_area_likely": is_mountain_area_likely,
        "location_profile": location_profile,
        "local_product_biases": local_product_biases,
    }


def _build_menu_gap_analysis(catalog: dict) -> dict:
    categories = catalog.get("categories", [])
    kinds_present = {
        str(category.get("kind")).strip().lower()
        for category in categories
        if category.get("kind") is not None
    }
    product_counts_by_kind: dict[str, int] = {}
    for category in categories:
        kind = str(category.get("kind") or "other").strip().lower()
        product_counts_by_kind[kind] = product_counts_by_kind.get(kind, 0) + int(category.get("product_count", 0) or 0)

    missing_kinds = [
        kind
        for kind in ("starter", "drink", "side", "dessert")
        if kind not in kinds_present
    ]

    expansion_priorities: list[str] = []
    if "main" in kinds_present and "drink" not in kinds_present:
        expansion_priorities.append("drink")
    if "main" in kinds_present and "dessert" not in kinds_present:
        expansion_priorities.append("dessert")
    if "main" in kinds_present and "side" not in kinds_present:
        expansion_priorities.append("side")
    if "main" in kinds_present and "starter" not in kinds_present:
        expansion_priorities.append("starter")

    return {
        "kinds_present": sorted(kinds_present),
        "missing_kinds": missing_kinds,
        "product_counts_by_kind": product_counts_by_kind,
        "expansion_priorities": expansion_priorities,
    }


def _normalize_search_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value.lower())).strip()


def _extract_topic_tokens(message: str) -> set[str]:
    tokens = {
        token
        for token in _normalize_search_text(message).split()
        if len(token) >= 3 and token not in SEARCH_TOPIC_STOPWORDS
    }
    return tokens


def _topic_overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = left & right
    denominator = max(len(left), len(right))
    if denominator <= 0:
        return 0.0
    return len(intersection) / denominator


def _build_search_cache_key(restaurant_id: int, message: str) -> str:
    topic = " ".join(sorted(_extract_topic_tokens(message)))
    normalized = topic or _normalize_search_text(message)
    return f"{restaurant_id}:{normalized}"


def _get_cached_web_context(restaurant_id: int, message: str) -> str | None:
    key = _build_search_cache_key(restaurant_id, message)
    cached_entry = WEB_SEARCH_RESPONSE_CACHE.get(key)
    if not cached_entry:
        return None

    if time.time() - float(cached_entry["created_at"]) > WEB_SEARCH_CACHE_TTL_SECONDS:
        WEB_SEARCH_RESPONSE_CACHE.pop(key, None)
        return None

    return str(cached_entry["answer"])


def _set_cached_web_context(restaurant_id: int, message: str, answer: str) -> None:
    key = _build_search_cache_key(restaurant_id, message)
    WEB_SEARCH_RESPONSE_CACHE[key] = {
        "answer": answer,
        "created_at": time.time(),
    }


def _should_use_web_search(message: str) -> bool:
    normalized_message = message.strip().lower()
    if not normalized_message:
        return False
    return any(re.search(pattern, normalized_message) for pattern in WEB_SEARCH_TRIGGER_PATTERNS)


def _build_web_search_tool(restaurant: Restaurant) -> dict:
    address = restaurant.address
    city = str(address.city).strip() if address and address.city else None
    country = _to_iso_country_code(address.country if address else None)
    tool: dict = {
        "type": "web_search",
        "user_location": {
            "type": "approximate",
            "timezone": restaurant.timezone,
        },
    }
    if city:
        tool["user_location"]["city"] = city
        tool["user_location"]["region"] = city
    if country:
        tool["user_location"]["country"] = country
    return tool


def _build_catalog_context(db: Session, restaurant_id: int) -> dict:
    rows = (
        db.query(
            Category.name.label("category_name"),
            Category.kind.label("category_kind"),
            Product.name.label("product_name"),
            Product.price.label("product_price"),
            Product.description.label("product_description"),
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
    all_product_names: list[str] = []
    all_category_names: list[str] = []
    for row in rows:
        all_product_names.append(row.product_name)
        if row.category_name not in all_category_names:
            all_category_names.append(row.category_name)
        bucket = grouped.setdefault(
            row.category_name,
            {
                "kind": row.category_kind,
                "products": [],
            },
        )
        bucket["products"].append(
            {
                "name": row.product_name,
                "price": float(row.product_price),
                "description": row.product_description,
            }
        )

    catalog = []
    for category_name, data in grouped.items():
        catalog.append(
            {
                "category_name": category_name,
                "kind": data["kind"],
                "products": data["products"],
                "product_count": len(data["products"]),
            }
        )
    return {
        "categories": catalog,
        "category_count": len(catalog),
        "product_count": len(all_product_names),
        "all_category_names": all_category_names,
        "all_product_names": all_product_names,
        "style_profile": _infer_style_profile(all_category_names, all_product_names),
    }


def _build_restaurant_context(db: Session, restaurant: Restaurant) -> dict:
    now = _get_local_now(restaurant.timezone)
    address = restaurant.address
    catalog = _build_catalog_context(db, restaurant.id)
    geography = _infer_geographic_profile(address)
    menu_gap_analysis = _build_menu_gap_analysis(catalog)
    return {
        "restaurant": {
            "id": restaurant.id,
            "name": restaurant.name,
            "timezone": restaurant.timezone,
            "street": address.street if address else None,
            "city": address.city if address else None,
            "country": address.country if address else None,
            "postal_code": address.postal_code if address else None,
            "season_hint": _season_hint(address.country if address else None, now),
            "current_month": now.strftime("%B"),
            "geography": geography,
        },
        "catalog": catalog,
        "menu_gap_analysis": menu_gap_analysis,
        "analytics": {
            "revenue": get_revenue_analytics(db, restaurant.id),
            "orders": get_order_analytics(db, restaurant.id),
            "customers": get_customer_analytics(db, restaurant.id),
            "performance": get_performance_analytics(db, restaurant.id),
        },
    }


def _build_system_prompt() -> str:
    return (
        "Tu es le bras droit du restaurateur et tu parles comme un membre interne de l'equipe.\n"
        "Tu utilises 'nous', 'notre', 'nos' et jamais 'vous' pour parler du restaurant.\n"
        "Tu reponds uniquement dans le cadre du restaurant fourni.\n"
        "Tu t'appuies en priorite sur tout le catalogue, toutes les analytics et le contexte du restaurant.\n"
        "Tu dois tenir compte du style culinaire observe dans la carte actuelle, des categories existantes, des produits deja vendus, "
        "de la saison en cours et de la localisation.\n"
        "Quand une recherche web est disponible, utilise-la pour capter les tendances actuelles, la concurrence locale et les pistes fournisseurs utiles a la decision.\n"
        "Tu dois aussi analyser la construction de carte: ce qui manque aujourd'hui, ce qui peut completer l'offre et ce qui peut faire monter le panier moyen.\n"
        "La localisation inclut la ville, le code postal, le pays et les signaux geographiques fournis. "
        "Utilise-les pour raisonner sur les produits plausibles localement, par exemple une logique bord de mer, montagne ou interieur, "
        "mais seulement si cela reste coherent avec notre carte actuelle.\n"
        "Si nous proposons un nouveau produit, il doit rester coherent avec l'identite de la carte. "
        "Ne suggere jamais un plat hors univers du restaurant.\n"
        "Ne suggere pas un produit saisonnier incoherent avec la saison actuelle ni un produit qui contredit clairement "
        "les habitudes de la carte existante.\n"
        "Le contexte geographique peut renforcer une recommandation, mais il ne doit jamais suffire a lui seul a justifier un produit "
        "qui ne correspond pas deja a notre style culinaire.\n"
        "Si la carte a un manque structurel evident, par exemple aucune boisson ou aucun dessert autour de plats principaux, "
        "priorise d'abord ce manque avant de proposer une simple variante d'un produit deja present.\n"
        "Tu peux proposer des idees de produits, de carte, de saisonnalite ou de localisation, "
        "mais tu dois les presenter comme des recommandations business et non comme des faits certains "
        "si les donnees ne prouvent pas directement le point.\n"
        "Quand nous recommandons une nouveaute, explique brievement pourquoi elle colle a notre carte et a nos ventes.\n"
        "Si la question porte sur un nouveau plat ou une extension de carte, appuie-toi explicitement sur les categories, produits "
        "et tendances deja visibles dans nos donnees.\n"
        "Quand plusieurs pistes sont possibles, donne au maximum 2 recommandations prioritaires, pas plus.\n"
        "Commence par la meilleure recommandation, puis eventuellement une deuxieme si elle est vraiment utile.\n"
        "Ne liste pas 4 ou 5 idees. Ne pars pas dans plusieurs directions a la fois.\n"
        "Pour une demande de modification de carte, d'ajout produit, de dessert ou boisson a lancer, de fournisseurs ou de concurrence locale, "
        "utilise la recherche web si elle est disponible afin de completer nos donnees internes avec de l'information actuelle.\n"
        "Si des fournisseurs peuvent aider, propose seulement des pistes credibles et prudentes: types de fournisseurs, "
        "grossistes specialises ou importateurs a valider localement. N'invente jamais de partenariat confirme ni d'information fournisseur non verifiee.\n"
        "Ne donne jamais de nom, d'adresse ou de coordonnees precises de fournisseur si ces informations ne sont pas presentes dans le contexte fourni. "
        "Si nous voulons des fournisseurs nommes et localises, dis clairement qu'une recherche web ou annuaire verifie est necessaire.\n"
        "Si tu mentionnes des fournisseurs, fais-le de facon breve et uniquement en lien direct avec la recommandation principale.\n"
        "Si une question depasse les donnees disponibles, dis-le clairement puis propose des hypotheses utiles.\n"
        "N'invente jamais de chiffres.\n"
        "Reponds dans la langue du client, avec un ton professionnel, concret, fluide et naturel.\n"
        "Va droit au but.\n"
        "Les reponses doivent etre courtes et utiles. Vise une reponse compacte en 3 a 6 phrases dans la plupart des cas.\n"
        "N'utilise pas de titres automatiques comme 'Reponse courte', 'Pourquoi' ou 'Action conseillee' sauf si c'est vraiment utile.\n"
        "N'utilise pas de markdown decoratif.\n"
        "N'utilise pas de listes a puces sauf si la question demande explicitement une liste.\n"
        "N'utilise pas de texte en gras, donc pas de **...**.\n"
        "N'ecris pas 'je vous conseille', 'je vous recommande' ou 'vous devriez'. "
        "Prefere des formulations comme 'nous pouvons', 'nous avons interet a', 'notre meilleure piste est'.\n"
        "Fais des paragraphes compacts dans un texte continu, sans sauts de ligne inutiles.\n"
        "Ecris comme dans une vraie conversation avec un restaurateur.\n"
    )


def _build_user_input(
    payload: AIChatRequest,
    context: dict,
    reused_web_context: str | None = None,
    cached_web_context: str | None = None,
) -> str:
    history = _serialize_history(payload.history)
    compact_context = json.dumps(context, ensure_ascii=True, default=str)
    compact_history = json.dumps(history, ensure_ascii=True, default=str)
    extra_sections: list[str] = []
    if reused_web_context:
        extra_sections.append(f"Contexte recent deja etabli dans cette conversation:\n{reused_web_context}")
    if cached_web_context:
        extra_sections.append(f"Contexte cache utile a reutiliser:\n{cached_web_context}")

    extra_block = "\n\n".join(extra_sections)
    return (
        f"Question du restaurateur:\n{payload.message.strip()}\n\n"
        f"Historique recent:\n{compact_history}\n\n"
        f"Contexte restaurant:\n{compact_context}"
        f"{f'\n\n{extra_block}' if extra_block else ''}"
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


def _normalize_answer_text(answer: str) -> str:
    return " ".join(answer.split())


def _extract_usage(response_json: dict) -> tuple[int, int, int]:
    usage = response_json.get("usage", {})
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


def _response_used_web_search(response_json: dict) -> bool:
    for item in response_json.get("output", []):
        if item.get("type") == "web_search_call":
            return True
    return False


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
    should_use_web_search = _should_use_web_search(payload.message)
    cached_web_context = None
    if should_use_web_search:
        cached_web_context = _get_cached_web_context(restaurant.id, payload.message)

    prepared_payload = AIChatRequest(
        conversation_id=payload.conversation_id,
        message=payload.message,
        history=history,
    )
    user_input = _build_user_input(
        prepared_payload,
        context,
        cached_web_context=cached_web_context,
    )
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
    if should_use_web_search and cached_web_context is None:
        body["tools"] = [_build_web_search_tool(restaurant)]
        body["tool_choice"] = "required"

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
    used_web_search = _response_used_web_search(response_json)
    answer = _normalize_answer_text(_extract_output_text(response_json))
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI returned an empty answer",
        )
    if should_use_web_search and used_web_search:
        _set_cached_web_context(restaurant.id, payload.message, answer)

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
