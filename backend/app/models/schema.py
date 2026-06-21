"""Typed contracts for the travel planner.

These models are the single source of truth shared by the API, the agents,
and the LangGraph state. Deterministic engines populate the structured fields;
LLMs only ever write the free-text `narrative`/`summary` fields.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums                                                                        #
# --------------------------------------------------------------------------- #
class FoodPreference(str, Enum):
    vegetarian = "vegetarian"
    non_vegetarian = "non_vegetarian"
    vegan = "vegan"
    jain = "jain"


class HotelCategory(str, Enum):
    budget = "budget"
    standard = "standard"
    premium = "premium"
    luxury = "luxury"


class Interest(str, Enum):
    nature = "nature"
    adventure = "adventure"
    shopping = "shopping"
    food = "food"
    heritage = "heritage"
    nightlife = "nightlife"
    family = "family"
    religious = "religious"
    wildlife = "wildlife"


# --------------------------------------------------------------------------- #
# Request                                                                      #
# --------------------------------------------------------------------------- #
class TravelRequest(BaseModel):
    source_country: str
    source_city: str = ""           # needed for domestic train/bus/cab routing
    destination_country: str
    destination_city: str
    duration_days: int = Field(ge=1, le=60)
    travelers: int = Field(ge=1, le=20, default=1)
    start_date: Optional[str] = None  # ISO date; optional for "anytime" planning
    budget_amount: float = Field(gt=0)
    budget_currency: str = "INR"
    food_preference: FoodPreference = FoodPreference.vegetarian
    hotel_category: HotelCategory = HotelCategory.standard
    language: str = "en"
    interests: list[Interest] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Agent outputs                                                                #
# --------------------------------------------------------------------------- #
class Place(BaseModel):
    name: str
    category: str  # must_visit | should_visit | optional
    tags: list[str] = Field(default_factory=list)
    note: str = ""


class DestinationResearch(BaseModel):
    must_visit: list[Place] = Field(default_factory=list)
    should_visit: list[Place] = Field(default_factory=list)
    optional: list[Place] = Field(default_factory=list)
    hidden_gems: list[str] = Field(default_factory=list)
    narrative: str = ""


class DaySlot(BaseModel):
    morning: list[str] = Field(default_factory=list)
    afternoon: list[str] = Field(default_factory=list)
    evening: list[str] = Field(default_factory=list)
    night: list[str] = Field(default_factory=list)


class ItineraryDay(BaseModel):
    day: int
    title: str
    slots: DaySlot
    est_walking_km: float = 0.0


class Itinerary(BaseModel):
    days: list[ItineraryDay] = Field(default_factory=list)
    narrative: str = ""


class CostLine(BaseModel):
    label: str
    amount_dest: float
    amount_source: float
    amount_usd: float


class CostBreakdown(BaseModel):
    source_currency: str
    dest_currency: str
    fx_source_to_dest: float
    fx_dest_to_usd: float
    lines: list[CostLine] = Field(default_factory=list)
    daily_budget_source: float = 0.0
    total_source: float = 0.0
    total_usd: float = 0.0
    within_budget: bool = True
    narrative: str = ""


class WeatherDay(BaseModel):
    date: str
    temp_c: float
    humidity_pct: float
    rain_probability_pct: float
    wind_kph: float
    summary: str


class WeatherReport(BaseModel):
    days: list[WeatherDay] = Field(default_factory=list)
    aqi: Optional[int] = None
    source: str = "offline"
    narrative: str = ""


class PackingList(BaseModel):
    clothing: list[str] = Field(default_factory=list)
    footwear: list[str] = Field(default_factory=list)
    accessories: list[str] = Field(default_factory=list)
    electronics: list[str] = Field(default_factory=list)
    medicines: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    narrative: str = ""


class TransportOption(BaseModel):
    mode: str
    approx_cost_dest: float
    typical_time_min: int
    note: str = ""


class TransportPlan(BaseModel):
    options: list[TransportOption] = Field(default_factory=list)
    source: str = "offline"
    narrative: str = ""


class HotelOption(BaseModel):
    name: str
    category: HotelCategory
    price_per_night_dest: float
    rating: float
    amenities: list[str] = Field(default_factory=list)
    distance_km_to_center: float = 0.0
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class HotelAdvice(BaseModel):
    recommended: list[HotelOption] = Field(default_factory=list)
    narrative: str = ""


class FoodAdvice(BaseModel):
    must_try_dishes: list[str] = Field(default_factory=list)
    restaurants: list[str] = Field(default_factory=list)
    street_food: list[str] = Field(default_factory=list)
    dietary_notes: str = ""
    source: str = "offline"
    narrative: str = ""


class VisaAdvice(BaseModel):
    required: bool
    visa_type: str = ""
    evisa_available: bool = False
    processing_days: int = 0
    recommended_apply_by: str = ""
    fee_per_traveler_usd: float = 0.0
    total_fee_usd: float = 0.0
    required_documents: list[str] = Field(default_factory=list)
    advisories: list[str] = Field(default_factory=list)
    advisory_score: Optional[float] = None
    advisory_source: str = "offline"
    narrative: str = ""


class EvaluationReport(BaseModel):
    confidence: float  # 0..1
    missing: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    uncertain_sections: list[str] = Field(default_factory=list)


class JourneyOption(BaseModel):
    mode: str                       # Flight | Train | Bus | Cab | Ferry
    name: str = ""                  # e.g. "Economy (cheapest)", "Rajdhani Express"
    approx_cost_source: float = 0.0  # per traveller, in the user's source currency
    approx_cost_usd: float = 0.0
    duration_hours: float = 0.0
    booking_url: str = ""           # clickable search/booking link
    note: str = ""


class JourneyPlan(BaseModel):
    domestic: bool = False
    from_label: str = ""
    to_label: str = ""
    options: list[JourneyOption] = Field(default_factory=list)
    airlines: list[str] = Field(default_factory=list)
    flight_estimate_usd: float = 0.0
    source: str = "offline"
    narrative: str = ""


# --------------------------------------------------------------------------- #
# Final plan                                                                   #
# --------------------------------------------------------------------------- #
class TravelPlan(BaseModel):
    request: TravelRequest
    destination: DestinationResearch
    itinerary: Itinerary
    cost: CostBreakdown
    weather: WeatherReport
    packing: PackingList
    transport: TransportPlan
    journey: "JourneyPlan"
    hotels: HotelAdvice
    food: FoodAdvice
    visa: VisaAdvice
    evaluation: EvaluationReport
    provider_used: str = "offline"
