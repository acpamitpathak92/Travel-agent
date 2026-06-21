"""Location helper tool. (Hotels moved to hotels.py; food/transport/flights/
weather/currency/maps each live in their own module.)"""
from __future__ import annotations

from app.mcp.base import tool


@tool("location.search_city", ttl=86400)
async def search_city(query: str) -> dict:
    return {"matches": [query.title()], "source": "offline"}
