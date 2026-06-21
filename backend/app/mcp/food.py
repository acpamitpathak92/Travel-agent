"""Food tools — live venues.

Live (no key): OpenStreetMap Overpass (restaurants/cafes/fast-food near the city,
               with diet tags honoured for veg/vegan/jain).
Live (keyed):  Google Places text search (set GOOGLE_MAPS_API_KEY).
Offline:       small static fallback.
"""
from __future__ import annotations

from app.config import settings
from app.llm.provider import get_client
from app.mcp.base import tool
from app.mcp.http import get_json, overpass
from app.mcp.maps import geocode
from app.logging_setup import get_logger

_log = get_logger("travel.food")

_DIET_TAG = {
    "vegetarian": "diet:vegetarian",
    "vegan": "diet:vegan",
    "jain": "diet:vegetarian",   # closest OSM proxy; flagged as approximate
}

_OFFLINE_DISHES = {
    "vegetarian": ["Local veg thali", "Grilled vegetables", "Paneer/tofu dish"],
    "non_vegetarian": ["Grilled local fish", "Regional curry", "Street kebabs"],
    "vegan": ["Plant bowl", "Coconut curry", "Fresh fruit platter"],
    "jain": ["Jain thali (no root veg)", "Plain rice & dal", "Fruit salad"],
}


def _offline(city: str, pref: str) -> dict:
    return {
        "must_try_dishes": _OFFLINE_DISHES.get(pref, _OFFLINE_DISHES["vegetarian"]),
        "restaurants": [f"{city} Garden Restaurant", f"Old Town Eatery, {city}"],
        "street_food": [f"{city} Night Market stalls", "Local food street"],
        "cuisines": [], "source": "offline",
    }


def parse_overpass_food(elements: list[dict], pref: str) -> dict:
    """Pure parser: split OSM elements into restaurants / street food, rank by diet."""
    diet_tag = _DIET_TAG.get(pref)
    restaurants: list[str] = []
    diet_first: list[str] = []
    street: list[str] = []
    cuisines: set[str] = set()
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        if tags.get("cuisine"):
            cuisines.update(c.strip() for c in tags["cuisine"].split(";")[:2])
        amenity = tags.get("amenity")
        if amenity in {"fast_food", "marketplace"}:
            if name not in street:
                street.append(name)
            continue
        matches_diet = diet_tag and tags.get(diet_tag) == "yes"
        if matches_diet and name not in diet_first:
            diet_first.append(name)
        elif name not in restaurants:
            restaurants.append(name)

    ranked = (diet_first + restaurants)[:8]
    dishes = [f"Local {c.replace('_', ' ')} cuisine" for c in list(cuisines)[:4]] or \
        _OFFLINE_DISHES.get(pref, _OFFLINE_DISHES["vegetarian"])
    return {
        "must_try_dishes": dishes,
        "restaurants": ranked or [],
        "street_food": street[:6],
        "cuisines": sorted(cuisines)[:8],
        "source": "live:osm",
    }


async def _overpass(city: str, pref: str) -> dict | None:
    loc = await geocode(query=city)
    if loc.get("lat") is None:
        return None
    lat, lon = loc["lat"], loc["lng"]
    q = (f"[out:json][timeout:20];("
         f'node["amenity"="restaurant"](around:4000,{lat},{lon});'
         f'node["amenity"="cafe"](around:4000,{lat},{lon});'
         f'node["amenity"="fast_food"](around:4000,{lat},{lon});'
         f'node["amenity"="marketplace"](around:4000,{lat},{lon});'
         f");out tags 80;")
    try:
        data = await overpass(q)
        parsed = parse_overpass_food(data.get("elements", []), pref)
        return parsed if parsed["restaurants"] or parsed["street_food"] else None
    except Exception:
        return None


async def _llm_food(city: str, country: str, pref: str, language: str = "en") -> dict | None:
    client = get_client()
    if not client.has_llm:
        return None
    prompt = (
        f"Real, currently-operating places to eat in {city}, {country} for a {pref} traveller. "
        f"Use genuine venue names that exist there. "
        f'Return JSON: {{"restaurants":["name (area)"],"street_food":["name/market (area)"],'
        f'"cuisines":["",""]}}. 6 restaurants, 4 street-food spots.')
    data = await client.complete_json(
        "You know real restaurants and food markets by name in cities worldwide.", prompt,
        lang=language)
    if not isinstance(data, dict):
        return None
    rest = [str(x) for x in (data.get("restaurants") or []) if str(x).strip()][:8]
    street = [str(x) for x in (data.get("street_food") or []) if str(x).strip()][:6]
    if not rest and not street:
        return None
    return {"must_try_dishes": [], "restaurants": rest, "street_food": street,
            "cuisines": [str(c) for c in (data.get("cuisines") or [])][:8],
            "source": "live:llm"}


async def _google_places(city: str, pref: str) -> dict | None:
    diet = "" if pref == "non_vegetarian" else pref + " "
    try:
        data = await get_json("https://maps.googleapis.com/maps/api/place/textsearch/json",
                              params={"query": f"{diet}restaurants in {city}",
                                      "key": settings.google_maps_api_key})
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            _log.warning("Google Places (food) status=%s: %s — enable the Places API for this key",
                         data.get("status"), data.get("error_message", ""))
        names = [r["name"] for r in data.get("results", [])][:8]
        if not names:
            return None
        sf = await get_json("https://maps.googleapis.com/maps/api/place/textsearch/json",
                            params={"query": f"street food in {city}",
                                    "key": settings.google_maps_api_key})
        street = [r["name"] for r in sf.get("results", [])][:6]
        return {"must_try_dishes": _OFFLINE_DISHES.get(pref, _OFFLINE_DISHES["vegetarian"]),
                "restaurants": names, "street_food": street, "cuisines": [],
                "source": "live:google"}
    except Exception:
        return None


@tool("food.search", ttl=3600)
async def search_food(city: str, food_preference: str, language: str = "en") -> dict:
    if settings.google_maps_api_key:
        g = await _google_places(city, food_preference)
        if g:
            return g
    osm = await _overpass(city, food_preference)
    if osm:
        return osm
    llm = await _llm_food(city, "", food_preference, language)
    if llm:
        return llm
    _log.warning("food: all live sources failed for %r -> offline placeholder", city)
    return _offline(city, food_preference)
