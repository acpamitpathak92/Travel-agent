"""Orchestration.

Topology:

    research ──► [ cost | weather | hotels | food | visa | transport ]  (parallel)
                                     │
                            ► packing (needs weather)
                            ► itinerary (needs research)
                                     │
                                  ► evaluation ──► TravelPlan

The canonical orchestrator is LangGraph. When LangGraph is not installed, an
equivalent bounded async fan-out runner is used so the pipeline always runs.
Both paths call the identical agent functions below.
"""
from __future__ import annotations

import asyncio

from app.agents import evaluation as eval_agent
from app.agents import journey as journey_agent
from app.agents import parallel as P
from app.agents import planning, research as research_agent
from app.config import settings
from app.graph.state import GraphState
from app.llm.provider import get_client
from app.logging_setup import get_logger
from app.mcp.base import gather_limited
from app.models.schema import TravelPlan, TravelRequest

_log = get_logger("travel.plan")


# --- node functions (shared by both orchestrators) ------------------------- #
async def n_research(state: GraphState) -> GraphState:
    return {"destination": await research_agent.run(state["request"])}


async def n_cost(state: GraphState) -> GraphState:
    return {"cost": await P.cost_agent(state["request"])}


async def n_weather(state: GraphState) -> GraphState:
    return {"weather": await P.weather_agent(state["request"])}


async def n_hotels(state: GraphState) -> GraphState:
    return {"hotels": await P.hotel_agent(state["request"])}


async def n_food(state: GraphState) -> GraphState:
    return {"food": await P.food_agent(state["request"])}


async def n_visa(state: GraphState) -> GraphState:
    return {"visa": await P.visa_agent(state["request"])}


async def n_transport(state: GraphState) -> GraphState:
    return {"transport": await P.transport_agent(state["request"])}


async def n_journey(state: GraphState) -> GraphState:
    return {"journey": await journey_agent.run(state["request"])}


async def n_packing(state: GraphState) -> GraphState:
    return {"packing": await planning.packing_agent(state["request"], state["weather"])}


async def n_itinerary(state: GraphState) -> GraphState:
    return {"itinerary": await planning.itinerary_agent(state["request"], state["destination"])}


async def n_eval(state: GraphState) -> GraphState:
    report = eval_agent.evaluate(
        state["request"], state["destination"], state["itinerary"],
        state["cost"], state["weather"], state["visa"],
    )
    return {"evaluation": report.model_dump()}


_PARALLEL = [n_cost, n_weather, n_hotels, n_food, n_visa, n_transport, n_journey]


# --- LangGraph builder (canonical) ----------------------------------------- #
def build_graph():
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(GraphState)
    g.add_node("research", n_research)
    for fn in _PARALLEL:
        g.add_node(fn.__name__, fn)
    g.add_node("packing", n_packing)
    g.add_node("itinerary", n_itinerary)
    g.add_node("evaluation", n_eval)

    g.add_edge(START, "research")
    for fn in _PARALLEL:
        g.add_edge("research", fn.__name__)        # fan-out
    g.add_edge("n_weather", "packing")
    g.add_edge("research", "itinerary")
    # converge: evaluation waits on every upstream node
    for name in [fn.__name__ for fn in _PARALLEL] + ["packing", "itinerary"]:
        g.add_edge(name, "evaluation")
    g.add_edge("evaluation", END)
    return g.compile()


# --- async fallback runner (equivalent semantics) -------------------------- #
async def _run_async(req: TravelRequest) -> GraphState:
    state: GraphState = {"request": req}
    state.update(await n_research(state))

    results = await gather_limited([fn(state) for fn in _PARALLEL], settings.max_parallel)
    for r in results:
        state.update(r)

    pack, itin = await asyncio.gather(n_packing(state), n_itinerary(state))
    state.update(pack); state.update(itin)
    state.update(await n_eval(state))
    return state


async def run_plan(req: TravelRequest) -> TravelPlan:
    try:
        graph = build_graph()
        state = await graph.ainvoke({"request": req})
    except Exception:
        state = await _run_async(req)

    from app.models.schema import EvaluationReport
    plan = TravelPlan(
        request=req,
        destination=state["destination"],
        itinerary=state["itinerary"],
        cost=state["cost"],
        weather=state["weather"],
        packing=state["packing"],
        transport=state["transport"],
        journey=state["journey"],
        hotels=state["hotels"],
        food=state["food"],
        visa=state["visa"],
        evaluation=EvaluationReport(**state["evaluation"]),
        provider_used=get_client().effective_provider,
    )
    _log.info(
        "PLAN %s->%s | llm=%s | weather=%s food=%s transport=%s journey=%s visa_adv=%s",
        req.source_city or req.source_country, req.destination_city,
        plan.provider_used, plan.weather.source, plan.food.source,
        plan.transport.source, plan.journey.source, plan.visa.advisory_source)
    offline = [s for s, v in {
        "weather": plan.weather.source, "food": plan.food.source,
        "transport": plan.transport.source, "journey": plan.journey.source,
        "visa_advisory": plan.visa.advisory_source}.items() if v == "offline"]
    if offline:
        _log.warning("Sections still OFFLINE: %s (see warnings above for why)",
                     ", ".join(offline))
    if plan.provider_used == "offline":
        _log.error("No LLM produced output — itinerary/food/hotels are placeholders. "
                   "Check /health/llm for the exact error.")
    return plan
