"""Agent 2 (Itinerary) and Agent 5 (Packing).

Itinerary is LLM-built (a real, geographically-grouped day plan using the
researched attractions), then deterministic code enforces the exact number of
days and fills any gaps. Packing is derived deterministically from weather.
"""
from __future__ import annotations

from app.llm.provider import get_client
from app.models.schema import (
    DaySlot, DestinationResearch, Itinerary, ItineraryDay, PackingList,
    TravelRequest, WeatherReport,
)

_SLOTS = ["morning", "afternoon", "evening", "night"]


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    return [str(v)] if v else []


async def _llm_itinerary(req: TravelRequest, names: list[str]) -> list[ItineraryDay] | None:
    client = get_client()
    prompt = (
        f"Build a realistic {req.duration_days}-day itinerary for "
        f"{req.destination_city}, {req.destination_country} for {req.travelers} traveller(s). "
        f"Use these real attractions where sensible: {', '.join(names[:14])}. "
        f"If the destination names a country, build the plan around its most-visited city. "
        f"Group each day geographically to minimise travel; include meals and downtime. "
        f"Return JSON: {{\"days\":[{{\"day\":1,\"title\":\"\",\"morning\":[\"\"],"
        f"\"afternoon\":[\"\"],\"evening\":[\"\"],\"night\":[\"\"]}}]}}. "
        f"Exactly {req.duration_days} day objects. Each activity max 12 words."
    )
    data = await client.complete_json(
        "You are an expert itinerary planner who sequences real places efficiently.", prompt,
        lang=req.language)
    if not isinstance(data, dict) or not isinstance(data.get("days"), list) or not data["days"]:
        return None
    days = []
    for i, d in enumerate(data["days"], start=1):
        if not isinstance(d, dict):
            continue
        slots = DaySlot(**{s: _as_list(d.get(s)) for s in _SLOTS})
        days.append(ItineraryDay(
            day=int(d.get("day", i)),
            title=str(d.get("title") or f"Day {i}: {req.destination_city}"),
            slots=slots, est_walking_km=round(3 + (i % 3) * 1.5, 1)))
    return days or None


def _fallback_days(req: TravelRequest, names: list[str]) -> list[ItineraryDay]:
    pool = names or [f"{req.destination_city} exploration"]
    days, idx = [], 0

    def take() -> list[str]:
        nonlocal idx
        item = pool[idx % len(pool)]
        idx += 1
        return [item]

    for d in range(1, req.duration_days + 1):
        slots = DaySlot(morning=take(), afternoon=take(),
                        evening=take() if d % 2 else [f"Leisure in {req.destination_city}"],
                        night=["Dinner & local stroll"])
        days.append(ItineraryDay(day=d, title=f"Day {d}: {req.destination_city}",
                                 slots=slots, est_walking_km=round(3 + (d % 3) * 1.5, 1)))
    return days


def _enforce_day_count(days: list[ItineraryDay], req: TravelRequest,
                       names: list[str]) -> list[ItineraryDay]:
    n = req.duration_days
    days = days[:n]
    for i in range(len(days), n):  # pad short plans
        days.append(_fallback_days(req, names)[i])
    for i, d in enumerate(days, start=1):  # renumber to be safe
        d.day = i
    return days


async def itinerary_agent(req: TravelRequest, research: DestinationResearch) -> Itinerary:
    names = [p.name for p in research.must_visit + research.should_visit + research.optional]
    days = await _llm_itinerary(req, names) or _fallback_days(req, names)
    days = _enforce_day_count(days, req, names)

    itinerary = Itinerary(days=days)
    itinerary.narrative = await get_client().narrate(
        "Itinerary Builder Agent",
        {"days": req.duration_days, "city": req.destination_city, "stops": names[:6]},
        lang=req.language)
    return itinerary


async def packing_agent(req: TravelRequest, weather: WeatherReport) -> PackingList:
    avg_temp = (sum(d.temp_c for d in weather.days) / len(weather.days)) if weather.days else 24
    max_rain = max((d.rain_probability_pct for d in weather.days), default=0)

    clothing = ["Light cotton layers"] if avg_temp >= 24 else ["Warm layers", "Light jacket"]
    if max_rain > 40:
        clothing.append("Waterproof jacket")
    interests = [i.value for i in req.interests]
    footwear = ["Walking shoes"]
    if "adventure" in interests or "nature" in interests:
        footwear.append("Trail/grip shoes")

    packing = PackingList(
        clothing=clothing, footwear=footwear,
        accessories=["Sunglasses", "Reusable water bottle", "Daypack"]
        + (["Umbrella"] if max_rain > 40 else []),
        electronics=["Phone & charger", "Universal power adapter", "Power bank"],
        medicines=["Personal medication", "Basic first-aid", "Motion-sickness tablets"],
        documents=["Passport", "Visa copy", "Travel insurance", "Hotel bookings", "ID"])
    packing.narrative = await get_client().narrate(
        "Packing Advisor Agent", {"avg_temp_c": round(avg_temp, 1), "rain_chance": max_rain},
        lang=req.language)
    return packing
