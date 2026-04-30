import math
import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "YumCoRestaurantApp/1.0"


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Retourne la distance en km entre deux points GPS (formule Haversine)."""
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _geocode_params(address: str) -> dict:
    return {
        "q": address,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }


def _normalize_country_code(country: str | None) -> str | None:
    if not country:
        return None

    normalized = country.strip().lower()
    aliases = {
        "fr": "fr",
        "france": "fr",
        "be": "be",
        "belgique": "be",
        "belgium": "be",
        "es": "es",
        "espagne": "es",
        "spain": "es",
        "it": "it",
        "italie": "it",
        "italy": "it",
        "de": "de",
        "allemagne": "de",
        "germany": "de",
        "pt": "pt",
        "portugal": "pt",
        "uk": "gb",
        "gb": "gb",
        "royaume-uni": "gb",
        "united kingdom": "gb",
    }

    if normalized in aliases:
        return aliases[normalized]
    if len(normalized) == 2 and normalized.isalpha():
        return normalized
    return None


def _address_fields(address: object) -> dict[str, str]:
    field_names = ("street", "city", "postal_code", "country")
    if isinstance(address, dict):
        return {
            field_name: str(address.get(field_name, "") or "").strip()
            for field_name in field_names
        }

    return {
        field_name: str(getattr(address, field_name, "") or "").strip()
        for field_name in field_names
    }


def _geocode_candidates(address: str | object) -> list[dict]:
    if isinstance(address, str):
        return [_geocode_params(address)]

    fields = _address_fields(address)
    street = fields["street"]
    city = fields["city"]
    postal_code = fields["postal_code"]
    country = fields["country"]
    country_code = _normalize_country_code(country)

    candidates: list[dict] = []

    structured_params = {
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }
    if street:
        structured_params["street"] = street
    if city:
        structured_params["city"] = city
    if postal_code:
        structured_params["postalcode"] = postal_code
    if country:
        structured_params["country"] = country
    if country_code:
        structured_params["countrycodes"] = country_code
    if any(structured_params.get(key) for key in ("street", "city", "postalcode", "country")):
        candidates.append(structured_params)

    queries = [
        ", ".join(part for part in (street, f"{postal_code} {city}".strip(), country) if part),
        ", ".join(part for part in (f"{postal_code} {city}".strip(), country) if part),
        ", ".join(part for part in (city, country) if part),
    ]
    for query in queries:
        if not query:
            continue
        params = _geocode_params(query)
        if country_code:
            params["countrycodes"] = country_code
        candidates.append(params)

    unique_candidates: list[dict] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for params in candidates:
        signature = tuple(sorted((key, str(value)) for key, value in params.items()))
        if signature in seen:
            continue
        seen.add(signature)
        unique_candidates.append(params)
    return unique_candidates


def _extract_geocode_result(data: list, original_query: str) -> dict:
    if not data:
        raise ValueError(f"Adresse introuvable : {original_query}")
    return {
        "lat": float(data[0]["lat"]),
        "lng": float(data[0]["lon"]),
        "place_name": data[0]["display_name"],
    }


async def geocode_address(address: str) -> dict:
    """Géocode une adresse texte → {lat, lng, place_name} via Nominatim."""
    async with httpx.AsyncClient() as client:
        for params in _geocode_candidates(address):
            response = await client.get(
                f"{NOMINATIM_URL}/search",
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            data = response.json()
            if data:
                return _extract_geocode_result(data, str(address))
    raise ValueError(f"Adresse introuvable : {address}")


def geocode_address_sync(address: str | object) -> dict:
    """Géocode une adresse texte en mode synchrone."""
    with httpx.Client() as client:
        for params in _geocode_candidates(address):
            response = client.get(
                f"{NOMINATIM_URL}/search",
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            data = response.json()
            if data:
                return _extract_geocode_result(data, str(address))
    raise ValueError(f"Adresse introuvable : {address}")


async def find_cities_within_radius(lat: float, lng: float, radius_km: float) -> list[dict]:
    """Retourne les villes/villages dans un rayon autour d'un point GPS."""
    radius_deg = radius_km / 111
    bbox = f"{lng - radius_deg},{lat - radius_deg},{lng + radius_deg},{lat + radius_deg}"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{NOMINATIM_URL}/search",
            params={
                "q": "ville",
                "format": "json",
                "limit": 20,
                "addressdetails": 1,
                "viewbox": bbox,
                "bounded": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
    data = response.json()

    valid_types = {"city", "town", "village", "suburb"}
    cities = []

    for place in data:
        if place.get("type") not in valid_types:
            continue

        place_lat = float(place["lat"])
        place_lng = float(place["lon"])
        distance = _haversine(lat, lng, place_lat, place_lng)

        if distance > radius_km:
            continue

        addr = place.get("address", {})
        postal_code = addr.get("postcode", "")
        if not postal_code:
            continue

        if place["type"] == "suburb" and addr.get("city"):
            name = f"{addr['city']} - {place['name']}"
        elif addr.get("city"):
            name = addr["city"]
        elif addr.get("town"):
            name = addr["town"]
        elif addr.get("village"):
            name = addr["village"]
        else:
            name = place["name"]

        cities.append({
            "id": place["place_id"],
            "name": name,
            "postal_code": postal_code,
            "lat": place_lat,
            "lng": place_lng,
            "distance_km": round(distance, 1),
        })

    cities.sort(key=lambda c: c["distance_km"])
    return cities


async def get_delivery_cities(restaurant_address: dict, radius_km: float) -> dict:
    """
    Point d'entrée principal.
    restaurant_address : {"street", "city", "postal_code", "country"}
    Retourne {"coordinates": {...}, "cities": [...]}
    """
    full_address = (
        f"{restaurant_address['street']}, "
        f"{restaurant_address['postal_code']} {restaurant_address['city']}, "
        f"{restaurant_address['country']}"
    )

    coordinates = await geocode_address(full_address)
    cities = await find_cities_within_radius(
        coordinates["lat"], coordinates["lng"], radius_km
    )

    # S'assurer que la ville du restaurant est dans la liste
    restaurant_city_present = any(
        c["name"].lower() == restaurant_address["city"].lower()
        and c["postal_code"] == restaurant_address["postal_code"]
        for c in cities
    )
    if not restaurant_city_present:
        cities.insert(0, {
            "id": "restaurant_city",
            "name": restaurant_address["city"],
            "postal_code": restaurant_address["postal_code"],
            "lat": coordinates["lat"],
            "lng": coordinates["lng"],
            "distance_km": 0.0,
        })

    return {"coordinates": coordinates, "cities": cities}
