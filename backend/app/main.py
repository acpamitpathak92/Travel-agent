"""FastAPI surface + CLI demo.

  uvicorn app.main:app --reload      # API at /plan and /plan/stream
  python -m app.main                 # offline CLI demo, no keys needed
"""
from __future__ import annotations

import asyncio
import json

import app.mcp  # noqa: F401  (registers MCP adapters)
from app.graph.workflow import run_plan
from app.llm.provider import get_client
from app.models.schema import TravelPlan, TravelRequest

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse

    app = FastAPI(title="AI Travel Planner & Visa Assistant", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
        # CORSMiddleware,
        # allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        # allow_methods=["*"], allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        c = get_client()
        return {"status": "ok", "provider": c.provider, "model": c.model,
                "providers_tried_in_order": c._candidates(), "llm_configured": c.has_llm}

    @app.get("/health/llm")
    async def health_llm() -> dict:
        """Live check that the configured LLM key actually works."""
        c = get_client()
        if not c.has_llm:
            return {"ok": False, "provider": "offline",
                    "error": "No LLM provider/key configured. Set LLM_PROVIDER + a key in backend/.env."}
        try:
            text = await c.complete("You are a health check.", "Reply with the single word: ok")
            return {"ok": bool(text and text.strip()), "provider_used": c.effective_provider,
                    "model": c.model, "sample": (text or "").strip()[:60]}
        except Exception as exc:  # surface the real reason (bad key, network, model name)
            return {"ok": False, "provider": c.provider, "model": c.model, "error": str(exc)[:300]}

    @app.post("/plan", response_model=TravelPlan)
    async def plan(req: TravelRequest) -> TravelPlan:
        return await run_plan(req)

    @app.post("/plan/stream")
    async def plan_stream(req: TravelRequest) -> "StreamingResponse":
        async def gen():
            yield _sse("status", {"stage": "starting", "provider": get_client().provider})
            result = await run_plan(req)
            for section in ("destination", "weather", "cost", "hotels", "food",
                            "visa", "transport", "packing", "itinerary", "evaluation"):
                yield _sse(section, getattr(result, section).model_dump()
                           if hasattr(getattr(result, section), "model_dump")
                           else getattr(result, section))
            yield _sse("done", {"within_budget": result.cost.within_budget,
                                "confidence": result.evaluation.confidence})

        return StreamingResponse(gen(), media_type="text/event-stream")

    def _sse(event: str, data) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

except ImportError:  # FastAPI optional for CLI-only use
    app = None


async def _demo() -> None:
    client = get_client()
    print(f"LLM provider: {client.provider}  model: {client.model or '(default)'}  "
          f"llm_configured: {client.has_llm}")
    if not client.has_llm:
        print("  -> No LLM key detected. Set LLM_PROVIDER + a key in backend/.env "
              "for real itineraries.")
    req = TravelRequest(
        source_country="India", destination_country="UAE", destination_city="Dubai",
        duration_days=4, travelers=2, budget_amount=120000, budget_currency="INR",
        interests=["heritage", "food", "shopping"], hotel_category="premium",
    )
    plan = await run_plan(req)
    print(f"Provider: {plan.provider_used}")
    print(f"Trip: {req.destination_city}, {req.duration_days} days x {req.travelers}")
    print(f"Total: {plan.cost.total_source:.0f} {plan.cost.source_currency} "
          f"(~${plan.cost.total_usd:.0f})  within_budget={plan.cost.within_budget}")
    print("Cost lines:")
    for line in plan.cost.lines:
        print(f"  {line.label:18} {line.amount_source:>10.0f} {plan.cost.source_currency}")
    print(f"Visa: {plan.visa.visa_type} (eVisa={plan.visa.evisa_available}, "
          f"{plan.visa.processing_days}d)")
    print(f"Itinerary days: {len(plan.itinerary.days)}")
    print(f"Confidence: {plan.evaluation.confidence}  caveats={len(plan.evaluation.caveats)}")
    for c in plan.evaluation.caveats:
        print(f"  ! {c}")


if __name__ == "__main__":
    asyncio.run(_demo())
