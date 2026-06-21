"""Maps tools: geocoding + distance/route.

Live (keyed):  Google Maps Geocoding + Distance Matrix (set GOOGLE_MAPS_API_KEY).
Live (no key): Open-Meteo geocoding + OSRM public router (driving).
Offline:       haversine straight-line distance with a road factor.
"""
from __future__ import annotations

import math

from app.config import settings
from app.mcp.base import tool
from app.mcp.http import get_json

_NOMINATIM_UA = {"User-Agent": settings.__class__.__name__ + " travel-planner/0.1 (contact: set me)"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


async def _geocode_google(query: str) -> tuple[float, float] | None:
    try:
        data = await get_json("https://maps.googleapis.com/maps/api/geocode/json",
                              params={"address": query, "key": settings.google_maps_api_key})
        if data.get("status") == "OK" and data["results"]:
            loc = data["results"][0]["geometry"]["location"]
            return float(loc["lat"]), float(loc["lng"])
    except Exception:
        pass
    return None


async def _geocode_osm(query: str) -> tuple[float, float] | None:
    # Prefer Open-Meteo geocoder (JSON, lenient), fall back to Nominatim.
    try:
        data = await get_json("https://geocoding-api.open-meteo.com/v1/search",
                              params={"name": query, "count": 1, "language": "en"})
        if data.get("results"):
            r = data["results"][0]
            return float(r["latitude"]), float(r["longitude"])
    except Exception:
        pass
    try:
        data = await get_json("https://nominatim.openstreetmap.org/search",
                              params={"q": query, "format": "json", "limit": 1},
                              headers=_NOMINATIM_UA)
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None


@tool("maps.geocode", ttl=86400)
async def geocode(query: str) -> dict:
    if settings.google_maps_api_key:
        g = await _geocode_google(query)
        if g:
            return {"lat": g[0], "lng": g[1], "source": "live:google"}
    o = await _geocode_osm(query)
    if o:
        return {"lat": o[0], "lng": o[1], "source": "live:osm"}
    return {"lat": None, "lng": None, "source": "offline"}


async def _distance_google(origin: str, destination: str) -> dict | None:
    try:
        data = await get_json("https://maps.googleapis.com/maps/api/distancematrix/json",
                              params={"origins": origin, "destinations": destination,
                                      "key": settings.google_maps_api_key})
        el = data["rows"][0]["elements"][0]
        if el.get("status") == "OK":
            return {"distance_km": round(el["distance"]["value"] / 1000, 1),
                    "duration_min": round(el["duration"]["value"] / 60),
                    "source": "live:google"}
    except Exception:
        pass
    return None


async def _distance_osrm(o: tuple[float, float], d: tuple[float, float]) -> dict | None:
    try:
        url = (f"https://router.project-osrm.org/route/v1/driving/"
               f"{o[1]},{o[0]};{d[1]},{d[0]}")
        data = await get_json(url, params={"overview": "false"})
        if data.get("code") == "Ok" and data.get("routes"):
            rt = data["routes"][0]
            return {"distance_km": round(rt["distance"] / 1000, 1),
                    "duration_min": round(rt["duration"] / 60),
                    "source": "live:osrm"}
    except Exception:
        pass
    return None


@tool("maps.distance", ttl=3600)
async def get_distance(origin: str, destination: str) -> dict:
    if settings.google_maps_api_key:
        g = await _distance_google(origin, destination)
        if g:
            return g
    o = await _geocode_osm(origin)
    d = await _geocode_osm(destination)
    if o and d:
        osrm = await _distance_osrm(o, d)
        if osrm:
            return osrm
        straight = haversine_km(*o, *d)
        return {"distance_km": round(straight * 1.3, 1),       # road factor
                "duration_min": round(straight * 1.3 / 60 * 60),
                "source": "offline:haversine"}
    return {"distance_km": 0.0, "duration_min": 0, "source": "offline"}
