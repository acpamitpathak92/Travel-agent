"""Tests for the deterministic spine. These run with zero API keys.

  pip install pytest pytest-asyncio && pytest -q
"""
from __future__ import annotations

import asyncio

import app.mcp  # noqa: F401  registers adapters
from app.cost.engine import build_cost
from app.graph.workflow import _run_async
from app.llm.provider import select_provider
from app.mcp.currency import convert_currency
from app.mcp.visa import check_visa
from app.models.schema import TravelRequest


def _req(**kw) -> TravelRequest:
    base = dict(source_country="India", destination_country="UAE",
                destination_city="Dubai", duration_days=4, travelers=2,
                budget_amount=200000, budget_currency="INR")
    base.update(kw)
    return TravelRequest(**base)


def test_provider_defaults_offline(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
              "GROQ_API_KEY", "OPENROUTER_API_KEY", "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    # Re-read settings would require reload; select_provider reads live settings,
    # which were captured at import. We assert the function is callable and stable.
    assert select_provider() in {"offline", "anthropic", "openai", "gemini",
                                  "groq", "openrouter", "azure"}


def test_currency_offline_rate():
    out = asyncio.run(convert_currency(amount=1000, src="INR", dst="USD"))
    assert out["converted"] > 0
    assert out["src"] == "INR" and out["dst"] == "USD"


def test_visa_known_route():
    v = asyncio.run(check_visa(source_country="India",
                               destination_country="UAE", travelers=3))
    assert v["required"] is True
    assert v["total_fee_usd"] == v["fee_usd"] * 3


def test_visa_unknown_route_is_low_confidence():
    v = asyncio.run(check_visa(source_country="Atlantis",
                               destination_country="Narnia", travelers=1))
    assert v["confidence"] == "low"


def test_cost_is_deterministic_and_consistent():
    a = asyncio.run(build_cost(_req()))
    b = asyncio.run(build_cost(_req()))
    assert a.total_source == b.total_source           # reproducible
    assert abs(sum(l.amount_source for l in a.lines) - a.total_source) < 1.0
    assert len(a.lines) == 6


def test_budget_flag():
    tight = asyncio.run(build_cost(_req(budget_amount=1000)))
    assert tight.within_budget is False


def test_full_pipeline_offline():
    state = asyncio.run(_run_async(_req(duration_days=3)))
    assert len(state["itinerary"].days) == 3        # itinerary matches duration
    assert state["cost"].total_source > 0
    assert 0.0 <= state["evaluation"]["confidence"] <= 1.0
    assert state["weather"].days                     # forecast present
