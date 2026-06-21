"""Hotel tools.

Live (keyed): Google Places text search (real hotel names, ratings, price level).
Live (LLM):   the model suggests real hotels with realistic nightly prices.
Offline:      deterministic placeholder catalogue.

Prices are returned in the destination's local currency (derived from country).
"""
from __future__ import annotations

from app.config import settings
from app.llm.provider import get_client
from app.mcp.base import tool
from app.mcp.http import get_json
from app.utils.currency_map import country_to_currency
from app.logging_setup import get_logger

_log = get_logger("travel.hotels")

_BANDS = {  # nightly price bands by category, USD (for Places price_level mapping)
    "budget": (25, 60), "standard": (60, 130),
    "premium": (130, 260), "luxury": (260, 700),
}
_AMENITIES = {
    "budget": ["WiFi", "AC"],
    "standard": ["WiFi", "AC", "Breakfast", "Gym"],
    "premium": ["WiFi", "AC", "Breakfast", "Pool", "Spa"],
    "luxury": ["WiFi", "AC", "Breakfast", "Pool", "Spa", "Concierge", "Airport transfer"],
}


async def _places(city: str, country: str, category: str, count: int, ccy: str) -> dict | None:
    try:
        data = await get_json(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": f"{category} hotels in {city}, {country}",
                    "key": settings.google_maps_api_key})
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            _log.warning("Google Places (hotels) status=%s: %s — enable the Places API for this key",
                         data.get("status"), data.get("error_message", ""))
        results = data.get("results", [])[:count]
        if not results:
            return None
        lo, hi = _BANDS[category]
        usd_to_ccy = 1.0  # price kept in USD band; converted at cost layer if needed
        hotels = []
        for r in results:
            lvl = r.get("price_level")
            usd = lo + (hi - lo) * ((lvl / 4) if lvl is not None else 0.5)
            hotels.append({
                "name": r.get("name", "Hotel"), "category": category,
                "price_per_night_dest": round(usd, 2), "price_currency": "USD",
                "rating": float(r.get("rating", 4.0)),
                "amenities": _AMENITIES[category], "distance_km_to_center": 0.0})
        return {"hotels": hotels, "currency": "USD", "source": "live:google"}
    except Exception:
        return None


_TIER_HINT = {
    "budget": "cheap, no-frills hostels/2-star hotels",
    "standard": "comfortable 3-star hotels",
    "premium": "upscale 4-star hotels",
    "luxury": "5-star luxury hotels and resorts",
}


async def _llm(city: str, country: str, category: str, count: int, ccy: str,
               language: str = "en") -> dict | None:
    client = get_client()
    lo, hi = _BANDS[category]
    prompt = (
        f"List {count} real, currently-operating {_TIER_HINT.get(category, category)} "
        f"({category} tier) in {city}, {country}. They MUST match the {category} price tier "
        f"(roughly {lo}-{hi} USD/night) — do not list cheaper or pricier hotels. "
        f"Give a realistic average nightly price in {ccy}. "
        f'Return JSON: {{"hotels":[{{"name":"","price_per_night":0,"rating":0,'
        f'"amenities":["",""],"distance_km_to_center":0}}]}}.')
    data = await client.complete_json(
        "You know real hotels by name and their star tier and nightly rates.", prompt,
        lang=language)
    if not isinstance(data, dict) or not data.get("hotels"):
        return None
    hotels = []
    for h in data["hotels"][:count]:
        if not isinstance(h, dict) or not h.get("name"):
            continue
        hotels.append({
            "name": h["name"], "category": category,
            "price_per_night_dest": float(h.get("price_per_night") or 0) or 100.0,
            "price_currency": ccy,
            "rating": float(h.get("rating") or 4.0),
            "amenities": h.get("amenities") or _AMENITIES[category],
            "distance_km_to_center": float(h.get("distance_km_to_center") or 0)})
    return {"hotels": hotels, "currency": ccy, "source": "live:llm"} if hotels else None


def _stub(city: str, category: str, count: int, ccy: str) -> dict:
    lo, hi = _BANDS[category]
    seed = sum(ord(c) for c in city.lower())
    hotels = []
    for i in range(count):
        price = lo + ((seed + i * 37) % max(1, hi - lo))
        hotels.append({
            "name": f"{city} {category.title()} Stay {i + 1}", "category": category,
            "price_per_night_dest": float(price), "price_currency": ccy,
            "rating": round(3.5 + ((seed + i) % 15) / 10, 1),
            "amenities": _AMENITIES[category],
            "distance_km_to_center": round(0.5 + ((seed + i * 5) % 60) / 10, 1)})
    return {"hotels": hotels, "currency": ccy, "source": "offline"}


@tool("hotel.search", ttl=1800)
async def search_hotels(city: str, category: str, count: int = 3, country: str = "",
                        language: str = "en") -> dict:
    ccy = country_to_currency(country)
    if settings.google_maps_api_key:
        p = await _places(city, country, category, count, ccy)
        if p:
            return p
    llm = await _llm(city, country, category, count, ccy, language)
    if llm:
        return llm
    _log.warning("hotels: live sources failed for %r (%s) -> placeholder names", city, category)
    return _stub(city, category, count, ccy)
