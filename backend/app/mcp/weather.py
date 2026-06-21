"""Weather tools.

Live (no key): Open-Meteo geocoding + forecast + air-quality (us_aqi).
Live (keyed):  weatherapi.com (set WEATHER_API_KEY).
Offline:       deterministic seasonal heuristic.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.config import settings
from app.mcp.base import tool
from app.mcp.http import get_json

# WMO weather interpretation codes -> short text (subset; covers common cases).
_WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 71: "Light snow",
    73: "Snow", 75: "Heavy snow", 80: "Rain showers", 81: "Rain showers", 82: "Violent showers",
    85: "Snow showers", 95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Severe thunderstorm",
}


def wmo_text(code) -> str:
    try:
        return _WMO.get(int(code), "Unsettled")
    except (TypeError, ValueError):
        return "Unsettled"


def parse_open_meteo(daily: dict, days: int) -> list[dict]:
    """Pure parser for the Open-Meteo /v1/forecast `daily` block."""
    times = daily.get("time", [])
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])
    hum = daily.get("relative_humidity_2m_mean", [])
    pop = daily.get("precipitation_probability_max", [])
    wind = daily.get("wind_speed_10m_max", [])
    code = daily.get("weather_code", [])
    out = []
    for i in range(min(days, len(times))):
        hi = tmax[i] if i < len(tmax) else 25
        lo = tmin[i] if i < len(tmin) else hi
        out.append({
            "date": times[i],
            "temp_c": round((hi + lo) / 2, 1),
            "humidity_pct": float(hum[i]) if i < len(hum) and hum[i] is not None else 60.0,
            "rain_probability_pct": float(pop[i]) if i < len(pop) and pop[i] is not None else 0.0,
            "wind_kph": float(wind[i]) if i < len(wind) and wind[i] is not None else 10.0,
            "summary": wmo_text(code[i]) if i < len(code) else "Unsettled",
        })
    return out


def _seasonal(city: str, d: date) -> dict:
    seed = (sum(ord(c) for c in city.lower()) + d.month * 7) % 100
    base = 18 + (seed % 14)
    rain = (seed * 3) % 70
    return {
        "date": d.isoformat(), "temp_c": float(base),
        "humidity_pct": float(45 + (seed % 40)), "rain_probability_pct": float(rain),
        "wind_kph": float(6 + (seed % 18)),
        "summary": "Rain likely" if rain > 45 else "Mostly clear",
    }


async def _geocode(city: str) -> tuple[float, float] | None:
    try:
        data = await get_json("https://geocoding-api.open-meteo.com/v1/search",
                              params={"name": city, "count": 1, "language": "en"})
        results = data.get("results")
        if results:
            return float(results[0]["latitude"]), float(results[0]["longitude"])
    except Exception:
        pass
    return None


async def _open_meteo(city: str, days: int) -> tuple[list[dict], int | None] | None:
    coords = await _geocode(city)
    if not coords:
        return None
    lat, lon = coords
    try:
        data = await get_json("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "forecast_days": min(max(days, 1), 16),
            "timezone": "auto",
            "daily": ",".join([
                "temperature_2m_max", "temperature_2m_min", "relative_humidity_2m_mean",
                "precipitation_probability_max", "wind_speed_10m_max", "weather_code"]),
        })
        out = parse_open_meteo(data.get("daily", {}), days)
        if not out:
            return None
    except Exception:
        return None

    aqi = None
    try:
        aq = await get_json("https://air-quality-api.open-meteo.com/v1/air-quality",
                            params={"latitude": lat, "longitude": lon,
                                    "hourly": "us_aqi", "forecast_days": 1})
        series = [v for v in aq.get("hourly", {}).get("us_aqi", []) if v is not None]
        if series:
            aqi = int(sum(series) / len(series))
    except Exception:
        pass
    return out, aqi


async def _weatherapi(city: str, days: int) -> list[dict] | None:
    try:
        data = await get_json("https://api.weatherapi.com/v1/forecast.json", params={
            "key": settings.weather_api_key, "q": city, "days": min(days, 14)})
        out = []
        for fday in data["forecast"]["forecastday"][:days]:
            dd = fday["day"]
            out.append({
                "date": fday["date"], "temp_c": dd["avgtemp_c"],
                "humidity_pct": dd["avghumidity"],
                "rain_probability_pct": dd.get("daily_chance_of_rain", 0),
                "wind_kph": dd["maxwind_kph"], "summary": dd["condition"]["text"],
            })
        return out or None
    except Exception:
        return None


async def _archive(city: str, start: date, days: int) -> tuple[list[dict], int | None] | None:
    """Use last year's actuals for the same dates as a seasonal estimate when the
    trip is beyond the forecast horizon (Open-Meteo forecast only covers ~16 days)."""
    coords = await _geocode(city)
    if not coords:
        return None
    lat, lon = coords
    ref_year = start.year - 1 if start >= date.today() else start.year
    try:
        ref_start = start.replace(year=ref_year)
    except ValueError:  # Feb 29 guard
        ref_start = start.replace(year=ref_year, day=28)
    ref_end = ref_start + timedelta(days=max(days - 1, 0))
    try:
        data = await get_json("https://archive-api.open-meteo.com/v1/archive", params={
            "latitude": lat, "longitude": lon,
            "start_date": ref_start.isoformat(), "end_date": ref_end.isoformat(),
            "timezone": "auto",
            "daily": ",".join([
                "temperature_2m_max", "temperature_2m_min", "relative_humidity_2m_mean",
                "precipitation_sum", "wind_speed_10m_max"]),
        })
        daily = data.get("daily", {})
        times = daily.get("time", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        hum = daily.get("relative_humidity_2m_mean", [])
        precip = daily.get("precipitation_sum", [])
        wind = daily.get("wind_speed_10m_max", [])
        out = []
        for i in range(min(days, len(times))):
            hi = tmax[i] if i < len(tmax) and tmax[i] is not None else 22
            lo = tmin[i] if i < len(tmin) and tmin[i] is not None else hi
            pr = precip[i] if i < len(precip) and precip[i] is not None else 0
            out.append({
                # show the ACTUAL trip date, not the reference year
                "date": (start + timedelta(days=i)).isoformat(),
                "temp_c": round((hi + lo) / 2, 1),
                "humidity_pct": float(hum[i]) if i < len(hum) and hum[i] is not None else 65.0,
                "rain_probability_pct": float(min(pr * 15, 95)),  # proxy from rainfall mm
                "wind_kph": float(wind[i]) if i < len(wind) and wind[i] is not None else 12.0,
                "summary": ("Rain likely" if pr > 2 else "Showers possible" if pr > 0.2
                            else "Mostly dry"),
            })
        return (out, None) if out else None
    except Exception:
        return None


@tool("weather.forecast", ttl=1800)
async def get_forecast(city: str, start_date: str | None, days: int) -> dict:
    start = datetime.fromisoformat(start_date).date() if start_date else date.today()
    days_ahead = (start - date.today()).days
    aqi = None
    out: list[dict] = []
    source = "offline"

    # Beyond the live-forecast horizon (or a past date) -> seasonal estimate from
    # last year's actuals for the same dates.
    if days_ahead > 14 or days_ahead < -1:
        arch = await _archive(city, start, days)
        if arch:
            out, aqi = arch[0], arch[1]
            source = "live:open-meteo-seasonal"

    if not out and settings.weather_api_key:
        wa = await _weatherapi(city, days)
        if wa:
            out, source = wa, "live:weatherapi"

    if not out:
        om = await _open_meteo(city, days)
        if om:
            out, aqi = om[0], om[1]
            source = "live:open-meteo"

    if not out:
        out = [_seasonal(city, start + timedelta(days=i)) for i in range(days)]
        aqi = (sum(ord(c) for c in city.lower()) % 5) * 40 + 20

    return {"days": out, "aqi": aqi, "source": source}
