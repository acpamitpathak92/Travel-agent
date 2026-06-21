"""Shared HTTP helper for MCP adapters: timeout, bounded retry, network gate.

When ALLOW_NETWORK is false, `get_json` raises immediately so adapters take
their offline path without waiting on socket timeouts (keeps tests fast).
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from app.config import settings
from app.logging_setup import get_logger

_log = get_logger("travel.http")


class NetworkDisabled(RuntimeError):
    pass


async def get_json(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    retries: int = 2,
    timeout: Optional[float] = None,
) -> Any:
    if not settings.allow_network:
        raise NetworkDisabled(url)
    last: Optional[Exception] = None
    async with httpx.AsyncClient(timeout=timeout or settings.request_timeout_s) as client:
        for attempt in range(retries + 1):
            try:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # retried/raised below
                last = exc
                await asyncio.sleep(0.25 * (attempt + 1))
    host = url.split("/")[2] if "//" in url else url
    _log.warning("GET %s failed after %d tries: %s", host, retries + 1,
                 f"{type(last).__name__}: {str(last)[:140]}")
    assert last is not None
    raise last


_OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]


async def overpass(query: str) -> Any:
    """Query Overpass across mirrors with a longer timeout (it's often slow)."""
    last: Optional[Exception] = None
    for url in _OVERPASS_MIRRORS:
        try:
            return await get_json(url, params={"data": query}, retries=0, timeout=30)
        except Exception as exc:  # try the next mirror
            last = exc
    if last:
        raise last
    raise RuntimeError("overpass: no mirrors")
