"""Journey agent — how to get from the source to the destination.

International: flight fare classes (Economy / Direct / Business) with Google
Flights booking links and an estimate per class.
Domestic (same country, e.g. within India): real intercity options — flight,
train, bus, cab — via the LLM, each with a booking/search link.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from app.llm.provider import get_client
from app.models.schema import JourneyOption, JourneyPlan, TravelRequest
from app.mcp.currency import convert_currency
from app.mcp.flights import search_flights


def _is_domestic(req: TravelRequest) -> bool:
    return req.source_country.strip().lower() == req.destination_country.strip().lower()


def _gflights(origin: str, dest: str, date: str | None, extra: str = "") -> str:
    q = f"Flights from {origin} to {dest}"
    if date:
        q += f" on {date}"
    if extra:
        q += f" {extra}"
    return "https://www.google.com/travel/flights?q=" + quote_plus(q)


def _gsearch(text: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(text)


def _book_url(mode: str, origin: str, dest: str, date: str | None) -> str:
    m = mode.lower()
    if "flight" in m:
        return _gflights(origin, dest, date)
    if "train" in m:
        return _gsearch(f"trains from {origin} to {dest} book tickets IRCTC")
    if "bus" in m:
        return _gsearch(f"bus tickets {origin} to {dest} redBus")
    if "cab" in m or "taxi" in m:
        return _gsearch(f"outstation cab {origin} to {dest} booking")
    return _gsearch(f"{mode} {origin} to {dest}")


async def _usd_to_source(usd: float, source_ccy: str) -> float:
    if usd <= 0 or source_ccy == "USD":
        return round(usd, 2)
    out = await convert_currency(amount=usd, src="USD", dst=source_ccy)
    return round(out["converted"], 2)


async def _llm_domestic(req: TravelRequest, origin: str) -> list[JourneyOption] | None:
    client = get_client()
    if not client.has_llm:
        return None
    prompt = (
        f"Intercity travel options from {origin} to {req.destination_city}, "
        f"{req.destination_country} for {req.travelers} traveller(s). Include the realistic "
        f"modes that actually connect these cities: flight, train, intercity bus, and cab/taxi. "
        f"For {req.destination_country}, name real services where possible (e.g. specific train "
        f"names/classes, Volvo/AC buses, outstation cab). Give per-traveller cost in USD and "
        f"approximate duration in hours. "
        f'Return JSON: {{"options":[{{"mode":"","name":"","approx_cost_usd":0,'
        f'"duration_hours":0,"note":""}}]}}. 3-5 options, cheapest/most-common first.')
    data = await client.complete_json(
        "You know real intercity transport (flights, trains, buses, cabs) and fares.",
        prompt, lang=req.language)
    if not isinstance(data, dict) or not isinstance(data.get("options"), list):
        return None
    out = []
    for o in data["options"][:6]:
        if not isinstance(o, dict) or not o.get("mode"):
            continue
        usd = float(o.get("approx_cost_usd") or 0)
        mode = str(o["mode"]).title()
        out.append(JourneyOption(
            mode=mode, name=str(o.get("name") or ""),
            approx_cost_usd=round(usd, 2),
            approx_cost_source=await _usd_to_source(usd, req.budget_currency),
            duration_hours=float(o.get("duration_hours") or 0),
            booking_url=_book_url(mode, origin, req.destination_city, req.start_date),
            note=str(o.get("note") or "")[:80]))
    return out or None


async def _international_options(req: TravelRequest, origin: str, base_usd: float,
                                airlines: list[str]) -> list[JourneyOption]:
    dest = req.destination_city
    classes = [
        ("Economy (cheapest)", 1.0, "economy"),
        ("Direct / non-stop", 1.25, "nonstop"),
        ("Business class", 3.2, "business class"),
    ]
    options = []
    for label, mult, extra in classes:
        usd = round(base_usd * mult, 2)
        options.append(JourneyOption(
            mode="Flight", name=label, approx_cost_usd=usd,
            approx_cost_source=await _usd_to_source(usd, req.budget_currency),
            duration_hours=0.0,
            booking_url=_gflights(origin, dest, req.start_date, extra),
            note="Round-trip per traveller" + (f" · {', '.join(airlines[:3])}" if airlines else "")))
    return options


async def run(req: TravelRequest) -> JourneyPlan:
    domestic = _is_domestic(req)
    origin = req.source_city.strip() or req.source_country
    plan = JourneyPlan(domestic=domestic, from_label=origin,
                       to_label=f"{req.destination_city}, {req.destination_country}")

    flights = await search_flights(source_country=req.source_country,
                                   destination_city=req.destination_city,
                                   travelers=req.travelers)
    plan.flight_estimate_usd = round(flights["estimate_usd_round_trip"], 2)
    plan.airlines = flights.get("airlines", [])

    if domestic:
        options = await _llm_domestic(req, origin)
        if options:
            plan.options, plan.source = options, "live:llm"
        else:
            plan.source = "offline"
            for mode, hrs, usd, note in [
                ("Flight", 2.0, flights["estimate_usd_round_trip"] / 2, "Fastest; add airport transfers"),
                ("Train", 12.0, 25, "Book early; AC classes recommended"),
                ("Bus", 14.0, 18, "Overnight AC/Volvo coaches"),
                ("Cab", 10.0, 80, "Private outstation cab; door to door"),
            ]:
                plan.options.append(JourneyOption(
                    mode=mode, approx_cost_usd=round(usd, 2),
                    approx_cost_source=await _usd_to_source(usd, req.budget_currency),
                    duration_hours=hrs,
                    booking_url=_book_url(mode, origin, req.destination_city, req.start_date),
                    note=note))
    else:
        plan.source = flights.get("source", "offline")
        plan.options = await _international_options(
            req, origin, flights["estimate_usd_round_trip"], plan.airlines)

    plan.narrative = await get_client().narrate(
        "Journey Agent",
        {"domestic": domestic, "from": origin, "to": req.destination_city,
         "modes": [o.mode for o in plan.options]}, lang=req.language)
    return plan
