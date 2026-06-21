"""Agents that run in parallel after destination research.

Each pulls deterministic data from MCP tools, assembles its typed output, and
adds an LLM narrative. They never depend on each other.
"""
from __future__ import annotations

from app.cost.engine import build_cost
from app.llm.provider import get_client
from app.models.schema import (
    CostBreakdown, FoodAdvice, HotelAdvice, HotelOption, TransportOption,
    TransportPlan, TravelRequest, VisaAdvice, WeatherDay, WeatherReport,
)
from app.mcp.hotels import search_hotels
from app.mcp.food import search_food
from app.mcp.transport import transport_options
from app.mcp.visa import check_visa, get_advisory
from app.mcp.weather import get_forecast


def _loc(req: TravelRequest) -> str:
    city, country = req.destination_city.strip(), req.destination_country.strip()
    if not country or city.lower() == country.lower() or city.lower() in country.lower():
        return city or country
    return f"{city}, {country}"


async def cost_agent(req: TravelRequest) -> CostBreakdown:
    breakdown = await build_cost(req)
    breakdown.narrative = await get_client().narrate(
        "Currency & Cost Agent",
        {"total_source": breakdown.total_source, "currency": breakdown.source_currency,
         "within_budget": breakdown.within_budget, "total_usd": breakdown.total_usd},
        lang=req.language,
    )
    return breakdown


async def weather_agent(req: TravelRequest) -> WeatherReport:
    data = await get_forecast(city=_loc(req),
                              start_date=req.start_date, days=req.duration_days)
    days = [WeatherDay(**d) for d in data["days"]]
    report = WeatherReport(days=days, aqi=data.get("aqi"), source=data.get("source", "offline"))
    report.narrative = await get_client().narrate(
        "Weather Agent",
        {"city": req.destination_city,
         "avg_temp": round(sum(d.temp_c for d in days) / max(len(days), 1), 1),
         "max_rain": max((d.rain_probability_pct for d in days), default=0)},
        lang=req.language,
    )
    return report


async def hotel_agent(req: TravelRequest) -> HotelAdvice:
    data = await search_hotels(city=req.destination_city,
                               category=req.hotel_category.value, count=3,
                               country=req.destination_country, language=req.language)
    options = []
    for h in data["hotels"]:
        options.append(HotelOption(
            **h,
            pros=["Central" if h["distance_km_to_center"] < 2 else "Quieter area",
                  "Good rating" if h["rating"] >= 4 else "Value pick"],
            cons=["Books up fast"] if h["rating"] >= 4.3 else ["Basic rooms"],
        ))
    advice = HotelAdvice(recommended=options)
    advice.narrative = await get_client().narrate(
        "Hotel Advisor Agent",
        {"category": req.hotel_category.value,
         "top": options[0].name if options else None},
        lang=req.language,
    )
    return advice


async def _llm_dishes(req: TravelRequest) -> list[str] | None:
    prompt = (
        f"List 5 must-try local dishes a {req.food_preference.value} traveller should eat in "
        f"{req.destination_city}, {req.destination_country}. Use real, specific dish names. "
        f'Return JSON: {{"dishes":["",""]}}.')
    data = await get_client().complete_json(
        "You know real regional cuisine and dish names.", prompt, lang=req.language)
    if isinstance(data, dict) and isinstance(data.get("dishes"), list):
        names = [str(d) for d in data["dishes"] if str(d).strip()][:6]
        return names or None
    return None


async def food_agent(req: TravelRequest) -> FoodAdvice:
    data = await search_food(city=_loc(req), food_preference=req.food_preference.value,
                             language=req.language)
    dishes = await _llm_dishes(req) or data["must_try_dishes"]
    advice = FoodAdvice(
        must_try_dishes=dishes, restaurants=data["restaurants"],
        street_food=data["street_food"],
        dietary_notes=f"Filtered for {req.food_preference.value} preference.",
        source=data.get("source", "offline"),
    )
    advice.narrative = await get_client().narrate(
        "Food Advisor Agent",
        {"pref": req.food_preference.value, "city": req.destination_city, "dishes": dishes},
        lang=req.language,
    )
    return advice


async def visa_agent(req: TravelRequest) -> VisaAdvice:
    v = await check_visa(source_country=req.source_country,
                         destination_country=req.destination_country,
                         travelers=req.travelers)
    advisory = await get_advisory(destination_country=req.destination_country,
                                  language=req.language)
    apply_by = "At least %d days before travel" % max(v["days"] * 2, 14)

    advisories = ["Visa rules change frequently — confirm on the official portal."]
    if advisory.get("message"):
        score = advisory.get("score")
        prefix = f"Advisory (risk {score}/5): " if score is not None else "Advisory: "
        advisories.insert(0, prefix + advisory["message"])

    advice = VisaAdvice(
        required=v["required"], visa_type=v["type"], evisa_available=v["evisa"],
        processing_days=v["days"], recommended_apply_by=apply_by,
        fee_per_traveler_usd=v["fee_usd"], total_fee_usd=v["total_fee_usd"],
        required_documents=v["docs"], advisories=advisories,
        advisory_score=advisory.get("score"),
        advisory_source=advisory.get("source", "offline"),
    )
    advice.narrative = await get_client().narrate(
        "Visa Advisor Agent",
        {"type": v["type"], "evisa": v["evisa"], "processing_days": v["days"],
         "advisory_score": advisory.get("score")},
        lang=req.language,
    )
    return advice


async def transport_agent(req: TravelRequest) -> TransportPlan:
    data = await transport_options(city=_loc(req), language=req.language)
    options = [TransportOption(**o) for o in data["options"]]
    plan = TransportPlan(options=options, source=data.get("source", "offline"))
    plan.narrative = await get_client().narrate(
        "Transportation Agent",
        {"modes": [o.mode for o in options]},
        lang=req.language,
    )
    return plan
