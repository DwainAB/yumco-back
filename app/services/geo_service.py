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


async def geocode_address(address: str) -> dict:
    """Géocode une adresse texte → {lat, lng, place_name} via Nominatim."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{NOMINATIM_URL}/search",
            params=_geocode_params(address),
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
    data = response.json()
    if not data:
        raise ValueError(f"Adresse introuvable : {address}")
    return {
        "lat": float(data[0]["lat"]),
        "lng": float(data[0]["lon"]),
        "place_name": data[0]["display_name"],
    }


def geocode_address_sync(address: str) -> dict:
    """Géocode une adresse texte en mode synchrone."""
    with httpx.Client() as client:
        response = client.get(
            f"{NOMINATIM_URL}/search",
            params=_geocode_params(address),
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
    data = response.json()
    if not data:
        raise ValueError(f"Adresse introuvable : {address}")
    return {
        "lat": float(data[0]["lat"]),
        "lng": float(data[0]["lon"]),
        "place_name": data[0]["display_name"],
    }


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
