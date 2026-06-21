"""Validate the live-response parsers against payloads shaped like the real
APIs (Open-Meteo, exchangerate-api, Travelpayouts). These run without network."""
from __future__ import annotations

import asyncio

import app.mcp  # noqa: F401  register adapters
from app.mcp.currency import convert_currency, parse_er_api
from app.mcp.flights import parse_cheap, search_flights
from app.mcp.maps import get_distance, haversine_km
from app.mcp.weather import get_forecast, parse_open_meteo, wmo_text


def test_parse_er_api_open_access_shape():
    payload = {"result": "success", "base_code": "INR",
               "rates": {"INR": 1, "USD": 0.0116, "AED": 0.0427}}
    assert parse_er_api(payload, "USD") == 0.0116
    assert parse_er_api(payload, "ZZZ") is None
    # keyed exchangerate-api uses conversion_rates
    assert parse_er_api({"result": "success", "conversion_rates": {"EUR": 0.9}}, "EUR") == 0.9


def test_parse_open_meteo_daily_arrays():
    daily = {
        "time": ["2026-06-21", "2026-06-22", "2026-06-23"],
        "temperature_2m_max": [38.0, 39.5, 40.0],
        "temperature_2m_min": [30.0, 31.0, 31.5],
        "relative_humidity_2m_mean": [55, 58, 60],
        "precipitation_probability_max": [10, 0, 25],
        "wind_speed_10m_max": [18.0, 20.0, 22.0],
        "weather_code": [1, 0, 95],
    }
    out = parse_open_meteo(daily, days=3)
    assert len(out) == 3
    assert out[0]["temp_c"] == 34.0            # (38+30)/2
    assert out[0]["summary"] == "Mainly clear"
    assert out[2]["summary"] == "Thunderstorm"
    assert out[2]["rain_probability_pct"] == 25.0


def test_wmo_text_handles_unknown():
    assert wmo_text(61) == "Light rain"
    assert wmo_text(123456) == "Unsettled"
    assert wmo_text(None) == "Unsettled"


def test_parse_cheap_travelpayouts_shape():
    payload = {"success": True, "data": {
        "DXB": {"0": {"price": 21000, "airline": "EK"},
                "1": {"price": 18500, "airline": "6E"}}}}
    assert parse_cheap(payload) == 18500.0
    assert parse_cheap({"success": False}) is None


def test_haversine_known_distance():
    # Pune -> Mumbai ~ 120 km straight line
    d = haversine_km(18.52, 73.86, 19.08, 72.88)
    assert 100 < d < 160


def test_adapters_report_offline_when_network_disabled():
    # conftest sets allow_network=False
    fx = asyncio.run(convert_currency(amount=100, src="INR", dst="USD"))
    assert fx["source"] == "offline" and fx["converted"] > 0

    wx = asyncio.run(get_forecast(city="Dubai", start_date=None, days=3))
    assert wx["source"] == "offline" and len(wx["days"]) == 3

    fl = asyncio.run(search_flights(source_country="India",
                                    destination_city="Dubai", travelers=1))
    assert fl["source"] == "offline" and fl["estimate_usd_round_trip"] > 0

    dist = asyncio.run(get_distance(origin="Pune", destination="Mumbai"))
    assert dist["source"].startswith("offline")


def test_parse_overpass_food_diet_ranking():
    from app.mcp.food import parse_overpass_food
    els = [
        {"tags": {"name": "Green Leaf", "amenity": "restaurant",
                  "diet:vegetarian": "yes", "cuisine": "indian"}},
        {"tags": {"name": "Grill House", "amenity": "restaurant", "cuisine": "bbq"}},
        {"tags": {"name": "Quick Bite", "amenity": "fast_food"}},
        {"tags": {"amenity": "restaurant"}},  # no name -> skipped
    ]
    out = parse_overpass_food(els, "vegetarian")
    assert out["restaurants"][0] == "Green Leaf"      # diet match ranked first
    assert "Quick Bite" in out["street_food"]
    assert "indian" in out["cuisines"]


def test_parse_overpass_modes_detection():
    from app.mcp.transport import parse_overpass_modes
    els = [{"tags": {"station": "subway"}}, {"tags": {"highway": "bus_stop"}},
           {"tags": {"amenity": "bicycle_rental"}}]
    modes = parse_overpass_modes(els)
    assert {"Metro", "Bus", "Bike share"} <= modes
    assert "Tram" not in modes


def test_parse_advisory_shape():
    from app.mcp.visa import parse_advisory
    data = {"data": {"AE": {"iso_alpha2": "AE", "name": "United Arab Emirates",
            "advisory": {"score": 2.1, "message": "Exercise normal caution.",
                         "updated": "2026-06-01", "source": "x"}}}}
    out = parse_advisory(data, "AE")
    assert out["score"] == 2.1 and "caution" in out["message"].lower()
    assert parse_advisory(data, "ZZ") is None
