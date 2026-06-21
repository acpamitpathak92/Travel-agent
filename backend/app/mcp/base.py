"""MCP-style tool boundary.

Every external capability is exposed as a `tool` with a stable name. Adapters
either call a real backend (its own MCP server or REST API) when configured, or
return deterministic offline data. The agents depend only on these tool names,
never on the transport, so swapping an in-process adapter for a remote MCP
server is a config change.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

_REGISTRY: dict[str, "Tool"] = {}
_CACHE: dict[str, tuple[float, Any]] = {}


class Tool:
    def __init__(self, name: str, fn: Callable[..., Awaitable[Any]], ttl: int) -> None:
        self.name = name
        self.fn = fn
        self.ttl = ttl

    async def __call__(self, **kwargs: Any) -> Any:
        key = self.name + "|" + "|".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        now = time.time()
        hit = _CACHE.get(key)
        if hit and now - hit[0] < self.ttl:
            return hit[1]
        result = await self.fn(**kwargs)
        _CACHE[key] = (now, result)
        return result


def tool(name: str, ttl: int = 900) -> Callable[[Callable[..., Awaitable[Any]]], Tool]:
    def deco(fn: Callable[..., Awaitable[Any]]) -> Tool:
        t = Tool(name, fn, ttl)
        _REGISTRY[name] = t
        return t
    return deco


def get_tool(name: str) -> Tool:
    return _REGISTRY[name]


def list_tools() -> list[str]:
    return sorted(_REGISTRY)


async def gather_limited(coros: list[Awaitable[Any]], limit: int) -> list[Any]:
    """Bounded fan-out used by the orchestrator's parallel stage."""
    sem = asyncio.Semaphore(limit)

    async def _run(c: Awaitable[Any]) -> Any:
        async with sem:
            return await c

    return await asyncio.gather(*[_run(c) for c in coros])
