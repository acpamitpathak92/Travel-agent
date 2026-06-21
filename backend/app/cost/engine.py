"""Deterministic budget math. No LLM — numbers must be reproducible.

Everything is computed in USD first (the baselines below are USD magnitudes),
then converted to the destination and source currencies. This avoids the unit
confusion that breaks for destinations like JPY/INR.
"""
from __future__ import annotations

from app.models.schema import CostBreakdown, CostLine, TravelRequest
from app.mcp.hotels import search_hotels
from app.mcp.transport import transport_options
from app.mcp.flights import search_flights
from app.mcp.currency import convert_currency
from app.mcp.visa import check_visa
from app.utils.currency_map import country_to_currency

_FOOD_USD_PER_DAY = {"budget": 18, "standard": 30, "premium": 55, "luxury": 90}
_ACTIVITY_USD_PER_DAY = 20.0


async def _to_usd(amount: float, ccy: str) -> float:
    if ccy == "USD":
        return amount
    return (await convert_currency(amount=amount, src=ccy, dst="USD"))["converted"]


async def build_cost(req: TravelRequest) -> CostBreakdown:
    dest_ccy = country_to_currency(req.destination_country)
    days, pax = req.duration_days, req.travelers

    # FX anchors.
    source_to_usd = (await convert_currency(amount=1, src=req.budget_currency, dst="USD"))["rate"]
    dest_to_usd = (await convert_currency(amount=1, src=dest_ccy, dst="USD"))["rate"]
    usd_to_dest = 1 / dest_to_usd if dest_to_usd else 1.0
    usd_to_source = 1 / source_to_usd if source_to_usd else 1.0

    # Accommodation — real hotel price, converted to USD from whatever currency it came in.
    h = await search_hotels(city=req.destination_city, category=req.hotel_category.value,
                            count=3, country=req.destination_country, language=req.language)
    if h["hotels"]:
        nightly_usd = await _to_usd(h["hotels"][0]["price_per_night_dest"],
                                    h.get("currency", "USD"))
    else:
        nightly_usd = 90.0

    food_usd = _FOOD_USD_PER_DAY[req.hotel_category.value]

    transport = (await transport_options(city=req.destination_city, language=req.language))["options"]
    paid = [o["approx_cost_dest"] for o in transport
            if o["typical_time_min"] and o["approx_cost_dest"] > 0]
    transport_day_usd = (min(paid) if paid else 5.0) * 4  # ~4 paid hops/day

    flights = await search_flights(source_country=req.source_country,
                                   destination_city=req.destination_city, travelers=req.travelers)
    flight_usd = flights["estimate_usd_round_trip"] * pax

    visa = await check_visa(source_country=req.source_country,
                            destination_country=req.destination_country, travelers=req.travelers)
    visa_usd = visa["total_fee_usd"]

    components_usd = {
        "Accommodation": nightly_usd * days,
        "Food": food_usd * days * pax,
        "Local transport": transport_day_usd * days,
        "Activities": _ACTIVITY_USD_PER_DAY * days * pax,
        "Flights (est.)": flight_usd,
        "Visa": visa_usd,
    }

    lines: list[CostLine] = []
    total_usd = 0.0
    for label, usd in components_usd.items():
        total_usd += usd
        lines.append(CostLine(
            label=label,
            amount_dest=round(usd * usd_to_dest, 2),
            amount_source=round(usd * usd_to_source, 2),
            amount_usd=round(usd, 2),
        ))

    total_source = round(total_usd * usd_to_source, 2)
    return CostBreakdown(
        source_currency=req.budget_currency,
        dest_currency=dest_ccy,
        fx_source_to_dest=round(source_to_usd * usd_to_dest, 4),
        fx_dest_to_usd=round(dest_to_usd, 4),
        lines=lines,
        daily_budget_source=round(total_source / max(days, 1), 2),
        total_source=total_source,
        total_usd=round(total_usd, 2),
        within_budget=total_source <= req.budget_amount,
    )
