"""Transport tools — live mode availability.

Live (no key): OpenStreetMap Overpass detects which modes actually exist in the
               city (metro / tram / bus / bike-share). Fares/times are labelled
               estimates — no free API publishes real-time fares.
Offline:       full generic mode list.
"""
from __future__ import annotations

from app.llm.provider import get_client
from app.mcp.base import tool
from app.mcp.http import overpass
from app.mcp.maps import geocode
from app.logging_setup import get_logger

_log = get_logger("travel.transport")

# mode -> (approx cost in dest currency units, typical minutes, note)
_BASE = {
    "Walking": (0.0, 30, "Free; central areas"),
    "Bus": (0.8, 40, "Estimated fare per ride"),
    "Metro": (1.5, 25, "Estimated fare per ride"),
    "Tram": (1.2, 28, "Estimated fare per ride"),
    "Bike share": (2.0, 20, "Estimated per ride"),
    "Taxi": (8.0, 20, "Estimated per short hop"),
    "Ride sharing": (6.0, 22, "Estimated per short hop"),
    "Rental car": (45.0, 0, "Estimated per day"),
}

_ALWAYS = ["Walking", "Taxi", "Ride sharing", "Rental car"]


def parse_overpass_modes(elements: list[dict]) -> set[str]:
    """Pure parser: which transit modes are present in the OSM result."""
    modes: set[str] = set()
    for el in elements:
        t = el.get("tags", {})
        if t.get("station") == "subway" or t.get("subway") == "yes":
            modes.add("Metro")
        if t.get("railway") == "tram_stop" or t.get("tram") == "yes":
            modes.add("Tram")
        if t.get("highway") == "bus_stop" or t.get("amenity") == "bus_station":
            modes.add("Bus")
        if t.get("amenity") == "bicycle_rental":
            modes.add("Bike share")
    return modes


def _build(modes: list[str], source: str) -> dict:
    options = []
    for m in modes:
        cost, mins, note = _BASE[m]
        options.append({"mode": m, "approx_cost_dest": cost,
                        "typical_time_min": mins, "note": note})
    return {"options": options, "source": source}


async def _overpass_modes(city: str) -> dict | None:
    loc = await geocode(query=city)
    if loc.get("lat") is None:
        return None
    lat, lon = loc["lat"], loc["lng"]
    q = (f"[out:json][timeout:20];("
         f'node["station"="subway"](around:6000,{lat},{lon});'
         f'node["railway"="tram_stop"](around:6000,{lat},{lon});'
         f'node["highway"="bus_stop"](around:6000,{lat},{lon});'
         f'node["amenity"="bicycle_rental"](around:6000,{lat},{lon});'
         f");out tags 200;")
    try:
        data = await overpass(q)
        detected = parse_overpass_modes(data.get("elements", []))
        ordered = [m for m in ["Walking", "Bus", "Metro", "Tram", "Bike share",
                               "Taxi", "Ride sharing", "Rental car"]
                   if m in detected or m in _ALWAYS]
        return _build(ordered, "live:osm")
    except Exception:
        return None


async def _llm_modes(city: str, language: str = "en") -> dict | None:
    client = get_client()
    if not client.has_llm:
        return None
    prompt = (
        f"Transport modes a tourist can use in {city}. Consider metro/subway, tram/light rail, "
        f"bus, suburban train, ferry, taxi, ride-hailing, bike share, rental car — include only "
        f"those that actually exist there. Give a typical fare in USD and typical trip minutes. "
        f'Return JSON: {{"modes":[{{"mode":"","approx_cost_usd":0,"typical_time_min":0,"note":""}}]}}.')
    data = await client.complete_json(
        "You know real city transport systems and approximate fares.", prompt, lang=language)
    if not isinstance(data, dict) or not isinstance(data.get("modes"), list):
        return None
    options = []
    for m in data["modes"][:8]:
        if not isinstance(m, dict) or not m.get("mode"):
            continue
        options.append({"mode": str(m["mode"]),
                        "approx_cost_dest": float(m.get("approx_cost_usd") or 0),
                        "typical_time_min": int(m.get("typical_time_min") or 0),
                        "note": (str(m.get("note") or "Estimated") + " (USD)")[:60]})
    return {"options": options, "source": "live:llm"} if options else None


@tool("transport.options", ttl=3600)
async def transport_options(city: str, language: str = "en") -> dict:
    live = await _overpass_modes(city)
    if live and live["options"]:
        return live
    llm = await _llm_modes(city, language)
    if llm:
        return llm
    _log.warning("transport: Overpass + LLM failed for %r -> generic offline modes", city)
    return _build(["Walking", "Bus", "Metro", "Taxi", "Ride sharing", "Rental car"], "offline")
