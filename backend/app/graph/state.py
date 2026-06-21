"""Shared graph state. Each node writes its own key; the parallel branch nodes
write disjoint keys so they can run concurrently without merge conflicts."""
from __future__ import annotations

from typing import Optional, TypedDict

from app.models.schema import (
    CostBreakdown, DestinationResearch, FoodAdvice, HotelAdvice, Itinerary,
    JourneyPlan, PackingList, TransportPlan, TravelRequest, VisaAdvice, WeatherReport,
)


class GraphState(TypedDict, total=False):
    request: TravelRequest
    destination: DestinationResearch
    cost: CostBreakdown
    weather: WeatherReport
    hotels: HotelAdvice
    food: FoodAdvice
    visa: VisaAdvice
    transport: TransportPlan
    journey: JourneyPlan
    packing: PackingList
    itinerary: Itinerary
    evaluation: Optional[dict]
