"""Currency tools.

Live (no key): open.er-api.com  ->  rates[dst].
Live (keyed):  v6.exchangerate-api.com (set FX_API_KEY) for higher quotas.
Offline:       static USD-pegged table.
"""
from __future__ import annotations

from app.config import settings
from app.mcp.base import tool
from app.mcp.http import get_json

# USD-pegged offline rates (1 USD = X). Labelled offline; clearly approximate.
_USD_RATES = {
    "USD": 1.0, "INR": 86.0, "EUR": 0.92, "GBP": 0.78, "JPY": 156.0,
    "AED": 3.67, "SGD": 1.35, "THB": 36.0, "AUD": 1.52, "CHF": 0.88,
}


def _offline_rate(src: str, dst: str) -> float:
    if src not in _USD_RATES or dst not in _USD_RATES:
        return 1.0
    return _USD_RATES[dst] / _USD_RATES[src]


def parse_er_api(data: dict, dst: str) -> float | None:
    """Pure parser for open.er-api.com / exchangerate-api latest payloads."""
    if data.get("result") == "success":
        rates = data.get("rates") or data.get("conversion_rates") or {}
        if dst in rates:
            return float(rates[dst])
    return None


@tool("currency.convert", ttl=3600)
async def convert_currency(amount: float, src: str, dst: str) -> dict:
    src, dst = src.upper(), dst.upper()
    rate: float | None = None
    source = "offline"

    if settings.fx_api_key:
        try:
            data = await get_json(
                f"https://v6.exchangerate-api.com/v6/{settings.fx_api_key}/pair/{src}/{dst}")
            if data.get("result") == "success" and data.get("conversion_rate"):
                rate, source = float(data["conversion_rate"]), "live"
        except Exception:
            pass

    if rate is None:
        try:
            data = await get_json(f"https://open.er-api.com/v6/latest/{src}")
            parsed = parse_er_api(data, dst)
            if parsed is not None:
                rate, source = parsed, "live"
        except Exception:
            pass

    if rate is None:
        rate = _offline_rate(src, dst)

    return {"src": src, "dst": dst, "rate": rate,
            "converted": round(amount * rate, 2), "source": source}


@tool("currency.usd", ttl=3600)
async def to_usd(amount: float, src: str) -> float:
    out = await convert_currency(amount=amount, src=src, dst="USD")
    return out["converted"]
