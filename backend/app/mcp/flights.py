"""Flight tools.

Live (keyed): Travelpayouts/Aviasales cheap-prices (set TRAVELPAYOUTS_TOKEN).
              IATA city codes resolved via the keyless places autocomplete.
Offline:      deterministic estimate seeded by route (no public keyless pricing).

Note: the Travelpayouts path is implemented to documented schemas but was not
exercised live here; verify with your token before relying on the numbers.
"""
from __future__ import annotations

from app.config import settings
from app.mcp.base import tool
from app.mcp.http import get_json


async def _iata(query: str) -> str | None:
    try:
        data = await get_json("https://autocomplete.travelpayouts.com/places2",
                              params={"term": query, "locale": "en", "types[]": "city"})
        if isinstance(data, list) and data:
            return data[0].get("code")
    except Exception:
        pass
    return None


def parse_cheap(data: dict) -> float | None:
    """Pure parser for /v1/prices/cheap: data[DEST][idx].price -> min price."""
    if not data.get("success"):
        return None
    prices = []
    for dest_block in (data.get("data") or {}).values():
        for entry in dest_block.values():
            if isinstance(entry, dict) and "price" in entry:
                prices.append(float(entry["price"]))
    return min(prices) if prices else None


def _offline_estimate(source_country: str, destination_city: str) -> float:
    seed = sum(ord(c) for c in (source_country + destination_city).lower())
    return float(180 + (seed % 600))  # USD round-trip, per traveller


@tool("flight.search", ttl=1800)
async def search_flights(source_country: str, destination_city: str, travelers: int) -> dict:
    source = "offline"
    per_traveller: float | None = None

    if settings.travelpayouts_token:
        origin = await _iata(source_country)
        dest = await _iata(destination_city)
        if origin and dest:
            try:
                data = await get_json("https://api.travelpayouts.com/v1/prices/cheap",
                                      params={"origin": origin, "destination": dest,
                                              "currency": "usd",
                                              "token": settings.travelpayouts_token})
                price = parse_cheap(data)
                if price:
                    per_traveller, source = price, "live:travelpayouts"
            except Exception:
                pass

    if per_traveller is None:
        per_traveller = _offline_estimate(source_country, destination_city)

    return {"estimate_usd_round_trip": round(per_traveller, 2),
            "airlines": ["IndiGo", "Emirates", "Singapore Airlines"][: 1 + sum(
                ord(c) for c in destination_city.lower()) % 3],
            "source": source}
