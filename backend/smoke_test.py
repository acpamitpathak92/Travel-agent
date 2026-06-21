"""Live smoke test: hits each adapter and prints whether it returned live or
offline data. Run on a connected machine:  python scripts_smoke.py
"""
import asyncio
import app.mcp  # noqa: F401
from app.mcp.currency import convert_currency
from app.mcp.weather import get_forecast
from app.mcp.food import search_food
from app.mcp.transport import transport_options
from app.mcp.visa import get_advisory
from app.mcp.maps import get_distance


async def main():
    rows = [
        ("currency", await convert_currency(amount=1000, src="INR", dst="USD")),
        ("weather", await get_forecast(city="Dubai", start_date=None, days=3)),
        ("food", await search_food(city="Dubai", food_preference="vegetarian")),
        ("transport", await transport_options(city="Dubai")),
        ("advisory", await get_advisory(destination_country="UAE")),
        ("maps", await get_distance(origin="Pune", destination="Mumbai")),
    ]
    print(f"{'adapter':10} {'source':22} sample")
    print("-" * 60)
    for name, r in rows:
        src = r.get("source", "?")
        sample = (r.get("converted") or (r.get("days") or [{}])[0].get("summary")
                  or (r.get("restaurants") or ["—"])[0]
                  or r.get("message") or r.get("distance_km"))
        print(f"{name:10} {src:22} {sample}")


if __name__ == "__main__":
    asyncio.run(main())
