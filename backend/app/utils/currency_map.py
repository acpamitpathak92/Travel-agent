"""Country -> ISO currency code. Used by the cost engine and hotel pricing so
destination amounts render in the local currency (e.g. Australia -> AUD)."""
from __future__ import annotations

COUNTRY_CCY = {
    "india": "INR", "united states": "USD", "usa": "USD", "us": "USD",
    "uae": "AED", "united arab emirates": "AED", "thailand": "THB",
    "singapore": "SGD", "japan": "JPY", "united kingdom": "GBP", "uk": "GBP",
    "australia": "AUD", "new zealand": "NZD", "canada": "CAD", "switzerland": "CHF",
    "germany": "EUR", "france": "EUR", "italy": "EUR", "spain": "EUR",
    "portugal": "EUR", "netherlands": "EUR", "ireland": "EUR", "greece": "EUR",
    "china": "CNY", "hong kong": "HKD", "south korea": "KRW", "korea": "KRW",
    "malaysia": "MYR", "indonesia": "IDR", "vietnam": "VND", "philippines": "PHP",
    "qatar": "QAR", "saudi arabia": "SAR", "turkey": "TRY", "egypt": "EGP",
    "south africa": "ZAR", "brazil": "BRL", "mexico": "MXN", "sri lanka": "LKR",
    "nepal": "NPR", "maldives": "MVR", "mauritius": "MUR", "sweden": "SEK",
    "norway": "NOK", "denmark": "DKK",
}


def country_to_currency(country: str, default: str = "USD") -> str:
    return COUNTRY_CCY.get((country or "").strip().lower(), default)
