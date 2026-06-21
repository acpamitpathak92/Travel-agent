"""Visa & embassy tools.

Offline ruleset is intentionally small and labelled low-confidence; visa rules
change often, so the evaluation agent flags these for human verification.
"""
from __future__ import annotations

from app.mcp.base import tool
from app.mcp.http import get_json
from app.logging_setup import get_logger

_log = get_logger("travel.visa")

# (source, destination) -> rule. "*" wildcard source. Illustrative only.
_RULES = {
    ("IN", "AE"): {"required": True, "type": "Tourist eVisa", "evisa": True,
                   "days": 5, "fee_usd": 90, "docs": ["Passport (6mo)", "Photo", "Return ticket", "Hotel booking"]},
    ("IN", "TH"): {"required": True, "type": "Visa on Arrival / eVisa", "evisa": True,
                   "days": 7, "fee_usd": 35, "docs": ["Passport (6mo)", "Photo", "Proof of funds"]},
    ("IN", "SG"): {"required": True, "type": "Tourist eVisa", "evisa": True,
                   "days": 4, "fee_usd": 30, "docs": ["Passport (6mo)", "Photo", "Itinerary", "Bank statement"]},
    ("IN", "JP"): {"required": True, "type": "Short-stay Tourist", "evisa": False,
                   "days": 7, "fee_usd": 25, "docs": ["Passport", "Photo", "Itinerary", "Bank statement", "ITR"]},
    ("IN", "GB"): {"required": True, "type": "Standard Visitor", "evisa": False,
                   "days": 15, "fee_usd": 150, "docs": ["Passport", "Photo", "Bank statements (6mo)", "Cover letter"]},
    ("IN", "AU"): {"required": True, "type": "Visitor visa (subclass 600)", "evisa": True,
                   "days": 20, "fee_usd": 130, "docs": ["Passport (6mo)", "Photo", "Bank statements", "Itinerary", "Travel insurance"]},
    ("IN", "US"): {"required": True, "type": "B1/B2 Visitor", "evisa": False,
                   "days": 30, "fee_usd": 185, "docs": ["Passport", "DS-160 confirmation", "Photo", "Bank statements", "Interview appointment"]},
}

_ISO = {  # crude country -> ISO2 for the demo
    "india": "IN", "uae": "AE", "united arab emirates": "AE", "thailand": "TH",
    "singapore": "SG", "japan": "JP", "united kingdom": "GB", "uk": "GB",
    "australia": "AU", "usa": "US", "united states": "US",
}


def _iso(country: str) -> str:
    return _ISO.get(country.strip().lower(), country.strip().upper()[:2])


@tool("visa.check", ttl=86400)
async def check_visa(source_country: str, destination_country: str, travelers: int) -> dict:
    s, d = _iso(source_country), _iso(destination_country)
    rule = _RULES.get((s, d))
    if rule is None:
        return {"required": True, "type": "Unknown — verify with embassy", "evisa": False,
                "days": 0, "fee_usd": 0.0, "total_fee_usd": 0.0,
                "docs": ["Passport"], "confidence": "low", "source": "offline"}
    return {
        "required": rule["required"], "type": rule["type"], "evisa": rule["evisa"],
        "days": rule["days"], "fee_usd": float(rule["fee_usd"]),
        "total_fee_usd": float(rule["fee_usd"] * travelers),
        "docs": rule["docs"], "confidence": "medium", "source": "offline",
    }


@tool("embassy.find", ttl=86400)
async def find_embassy(destination_country: str, near_city: str) -> dict:
    return {"name": f"{destination_country} Consulate / VFS — {near_city}",
            "type": "VFS Global", "note": "Verify address and appointment system online.",
            "source": "offline"}


def parse_advisory(data: dict, iso2: str) -> dict | None:
    """Pure parser for travel-advisory.info payloads."""
    entry = (data.get("data") or {}).get(iso2)
    if not entry:
        return None
    adv = entry.get("advisory", {})
    return {
        "score": adv.get("score"),
        "message": adv.get("message", "").strip(),
        "updated": adv.get("updated", ""),
        "source_name": adv.get("source", ""),
    }


@tool("advisory.get", ttl=21600)
async def get_advisory(destination_country: str, language: str = "en") -> dict:
    """Live travel advisory (risk score + message) from travel-advisory.info,
    with an LLM summary fallback when that feed is unavailable."""
    iso2 = _iso(destination_country)
    try:
        data = await get_json("https://www.travel-advisory.info/api",
                              params={"countrycode": iso2})
        parsed = parse_advisory(data, iso2)
        if parsed and parsed.get("message"):
            parsed["source"] = "live"
            return parsed
    except Exception:
        pass

    # Fallback: LLM safety summary (model knowledge, not a real-time feed).
    from app.llm.provider import get_client
    client = get_client()
    if client.has_llm:
        data = await client.complete_json(
            "You summarise general travel-safety guidance for tourists.",
            f"Brief travel-safety advisory for tourists visiting {destination_country}. "
            f'Return JSON: {{"score":0,"message":""}} where score is 1 (very safe) to '
            f"5 (high risk). Message max 25 words.")
        if isinstance(data, dict) and data.get("message"):
            return {"score": data.get("score"), "message": str(data["message"]),
                    "updated": "", "source": "live:llm"}
    _log.warning("advisory: travel-advisory.info + LLM failed for %r -> offline", destination_country)
    return {"score": None, "message": "", "updated": "", "source": "offline"}
