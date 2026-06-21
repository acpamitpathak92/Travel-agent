"""Agent 10 — Authenticity / Evaluation.

Deterministic checks across the assembled plan: missing data, contradictions,
low-confidence sources. Produces a 0..1 confidence score. The LLM is used only
to phrase caveats, never to compute the score.
"""
from __future__ import annotations

from app.models.schema import (
    CostBreakdown, DestinationResearch, EvaluationReport, Itinerary,
    TravelRequest, VisaAdvice, WeatherReport,
)


def evaluate(
    req: TravelRequest,
    research: DestinationResearch,
    itinerary: Itinerary,
    cost: CostBreakdown,
    weather: WeatherReport,
    visa: VisaAdvice,
) -> EvaluationReport:
    missing: list[str] = []
    contradictions: list[str] = []
    caveats: list[str] = []
    uncertain: list[str] = []

    if not research.must_visit:
        missing.append("No must-visit attractions resolved.")
    if len(itinerary.days) != req.duration_days:
        contradictions.append(
            f"Itinerary has {len(itinerary.days)} days but trip is {req.duration_days}.")
    if not weather.days:
        missing.append("No weather forecast available.")
    if cost.total_source <= 0:
        missing.append("Cost total did not compute.")
    if not cost.within_budget:
        caveats.append(
            f"Estimated cost ({cost.total_source:.0f} {cost.source_currency}) exceeds "
            f"the stated budget ({req.budget_amount:.0f}).")

    # Source-confidence flags (offline / low-confidence data).
    if visa.visa_type.startswith("Unknown"):
        uncertain.append("visa")
        caveats.append("Visa requirement could not be confirmed — verify with the embassy.")
    if cost.fx_source_to_dest == 1.0 and req.budget_currency != cost.dest_currency:
        uncertain.append("currency")

    # Confidence: start high, subtract for each issue class.
    confidence = 1.0
    confidence -= 0.15 * len(missing)
    confidence -= 0.15 * len(contradictions)
    confidence -= 0.08 * len(uncertain)
    confidence = max(0.0, round(confidence, 2))

    if confidence < 0.5:
        caveats.append("Several sections rely on offline estimates — treat as indicative.")

    return EvaluationReport(
        confidence=confidence, missing=missing, contradictions=contradictions,
        caveats=caveats, uncertain_sections=sorted(set(uncertain)),
    )
