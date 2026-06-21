"""Agent 1 — Destination Research.

LLM-driven: asks the model for REAL attractions for the specific city, returned
as structured JSON. Deterministic code dedups, caps, and assigns tiers. Falls
back to a generic stub only when no LLM is configured.
"""
from __future__ import annotations

from app.llm.provider import get_client
from app.models.schema import DestinationResearch, Interest, Place, TravelRequest

_FALLBACK = {
    Interest.heritage: ["Old Town", "Historic Fort", "National Museum"],
    Interest.nature: ["Botanical Gardens", "Riverside Park", "Scenic Viewpoint"],
    Interest.food: ["Central Food Market", "Spice Bazaar"],
    Interest.shopping: ["Grand Bazaar", "Designer District"],
    Interest.nightlife: ["Rooftop Bars", "Live Music Quarter"],
    Interest.adventure: ["Cable Car", "Kayak Point"],
    Interest.religious: ["Grand Temple", "Old Cathedral"],
    Interest.family: ["City Aquarium", "Theme Park"],
    Interest.wildlife: ["Wildlife Sanctuary", "Bird Park"],
}


def _places(items, category: str) -> list[Place]:
    out, seen = [], set()
    for it in items or []:
        name = (it.get("name") if isinstance(it, dict) else str(it)).strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(Place(name=name, category=category,
                         note=(it.get("note", "") if isinstance(it, dict) else "")))
    return out


async def _llm_research(req: TravelRequest) -> DestinationResearch | None:
    client = get_client()
    interests = ", ".join(i.value for i in req.interests) or "general sightseeing"
    prompt = (
        f"Real attractions for a {req.duration_days}-day trip to "
        f"{req.destination_city}, {req.destination_country}. Traveller interests: {interests}. "
        f"Use only genuine, well-known places that actually exist in or near this city. "
        f"If the destination names a country rather than a city, focus on its single "
        f"most-visited city and say which in each note. "
        f'Return JSON: {{"must_visit":[{{"name":"","note":""}}],'
        f'"should_visit":[{{"name":"","note":""}}],"optional":[{{"name":"","note":""}}],'
        f'"hidden_gems":["",""]}}. 4-6 must, 3-5 should, 2-4 optional, 2-3 hidden gems. '
        f"Notes max 12 words."
    )
    data = await client.complete_json(
        "You are an expert local travel guide with accurate destination knowledge.", prompt,
        lang=req.language)
    if not isinstance(data, dict) or not data.get("must_visit"):
        return None
    return DestinationResearch(
        must_visit=_places(data.get("must_visit"), "must_visit"),
        should_visit=_places(data.get("should_visit"), "should_visit"),
        optional=_places(data.get("optional"), "optional"),
        hidden_gems=[str(h) for h in (data.get("hidden_gems") or [])][:4],
    )


def _fallback(req: TravelRequest) -> DestinationResearch:
    must, should, optional = [], [], []
    interests = req.interests or [Interest.heritage, Interest.food]
    for i, interest in enumerate(interests):
        for j, name in enumerate(_FALLBACK.get(interest, [])):
            p = Place(name=f"{name} ({req.destination_city})", category="", tags=[interest.value])
            if i == 0 and j == 0:
                p.category = "must_visit"; must.append(p)
            elif j == 0:
                p.category = "should_visit"; should.append(p)
            else:
                p.category = "optional"; optional.append(p)
    if not must:
        must.append(Place(name=f"{req.destination_city} City Centre", category="must_visit"))
    return DestinationResearch(
        must_visit=must, should_visit=should, optional=optional,
        hidden_gems=[f"Local district in {req.destination_city}"])


async def run(req: TravelRequest) -> DestinationResearch:
    research = await _llm_research(req) or _fallback(req)
    research.narrative = await get_client().narrate(
        "Destination Research Agent",
        {"city": req.destination_city, "country": req.destination_country,
         "must": [p.name for p in research.must_visit]},
        lang=req.language,
    )
    return research
