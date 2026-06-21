# AI Travel Planner & Visa Assistant — Architectural Spine

A provider-agnostic, multi-agent travel-planning backend built on **LangGraph +
MCP-style tool boundaries + FastAPI**. It produces a complete `TravelPlan`
(destination research, day-wise itinerary, costed budget, weather, packing,
transport, hotels, food, visa) with an evaluation/confidence pass.

**Design principles** (deterministic where it matters, LLM only for prose):

- **Deterministic in code, LLM for narrative only.** All numbers — budget, FX,
  cost lines, confidence score, validation — are computed in plain Python and
  are reproducible. LLMs write only the `narrative` fields.
- **MCP tool boundary.** Every external capability is a named tool
  (`visa.check`, `currency.convert`, `weather.forecast`, …). Agents depend on
  tool names, not transports — swap an in-process adapter for a remote MCP
  server via config, no agent changes.
- **Env-driven provider selection.** Anthropic / OpenAI / Gemini / Groq /
  OpenRouter / Azure OpenAI / Ollama, auto-selected by which key is present.
- **Graceful offline fallback.** Runs end-to-end with **zero API keys** using
  deterministic offline data; the evaluation agent flags offline/low-confidence
  sections.
- **Parallel fan-out.** Independent agents run concurrently (LangGraph
  supersteps, or a bounded async runner when LangGraph isn't installed).

## Project layout

```
travel-planner/
  backend/     FastAPI + LangGraph + MCP adapters (Python)   ← .env lives here
  frontend/    Vite + React UI
```

## Quick start

**Backend**

```bash
cd backend
pip install -r requirements.txt
# .env is already included (live weather/FX/food/transport need no keys);
# add provider/API keys to it when you want them.

python -m app.main                       # offline CLI demo, prints a full plan
uvicorn app.main:app --reload            # API on :8000  (POST /plan, /plan/stream)
pytest -q                                # 16 tests, no keys needed
python smoke_test.py                     # prints live-vs-offline per adapter
```

**Frontend** (Vite + React, in `frontend/`)

```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

The form collects the trip details, calls `POST /plan` (Vite proxies it to the
backend on :8000), and renders the plan: a boarding-pass summary, day-wise
itinerary, cost dashboard, weather strip, visa + live advisory, food, transport,
hotels, packing, and a plan-check panel. Live sections show a **live/offline
badge**. Run the backend first; CORS is enabled for the dev server origin.

## Workflow

```
research ─► [ cost | weather | hotels | food | visa | transport ]   (parallel)
                              │
                     ► packing   (needs weather)
                     ► itinerary (needs research)
                              │
                          ► evaluation ─► TravelPlan
```

LangGraph is the canonical orchestrator (`build_graph()`); an equivalent async
fan-out runner is used automatically if LangGraph isn't installed. Both call the
identical agent node functions.

## Backend layout (`backend/`)

```
app/
  config.py            env settings (no hardcoded secrets)
  models/schema.py     Pydantic contracts (single source of truth)
  llm/provider.py      provider-agnostic client + auto-select + offline narrator
  mcp/                 MCP-style tool adapters (registry, TTL cache, live+offline)
    base.py  http.py  currency.py  weather.py  maps.py  flights.py  visa.py  catalog.py
  cost/engine.py       deterministic budget math
  agents/              10 agents (research, parallel branches, planning, evaluation)
  graph/               LangGraph state + workflow (+ async fallback)
  main.py              FastAPI app + streaming + CLI demo
tests/test_core.py     unit + full-pipeline tests
```

## Live data adapters

Every external capability degrades cleanly: **keyed provider → keyless live → offline**.

| Tool | Live, no key | Live, keyed | Offline fallback |
|------|--------------|-------------|------------------|
| `weather.forecast` | Open-Meteo (geocode + forecast + us_aqi) | `WEATHER_API_KEY` (weatherapi.com) | seasonal heuristic |
| `currency.convert` | open.er-api.com | `FX_API_KEY` (exchangerate-api v6) | static USD table |
| `food.search` | OpenStreetMap Overpass (real venues, diet tags) | `GOOGLE_MAPS_API_KEY` (Places) | small static list |
| `transport.options` | OSM Overpass (detects metro/tram/bus/bike that *exist*) | — | generic mode list |
| `maps.geocode` / `maps.distance` | OSM geocoder + OSRM router | `GOOGLE_MAPS_API_KEY` | haversine + road factor |
| `advisory.get` | travel-advisory.info (risk score + message) | — | none |
| `flight.search` | — (no keyless pricing exists) | `TRAVELPAYOUTS_TOKEN` | seeded estimate |
| `visa.check` | — (no reliable free real-time source) | (plug your source) | illustrative ruleset |

So **weather, currency, food, transport, maps and travel advisories return real data
with zero config**. Each response carries a `source` (`live:*` or `offline`); the
four traveller-facing sections (weather, food, transport, visa-advisory) surface
that as a **live/offline badge in the UI**, and the evaluation agent flags offline
sections.

**On "real-time":** weather/FX are genuinely current; food/transport/maps use
live community POI + routing data (current, not minute-by-minute departures);
advisories are daily-updated government risk data. Visa *requirements* stay a
flagged ruleset — no free API publishes them reliably, so the planner marks
unverified routes low-confidence rather than inventing rules. Hotel and flight
pricing have no free real-time source either (flights need a Travelpayouts token).

**Verification note:** live parsers are unit-tested against payloads shaped like
each real API (`tests/test_live_parsers.py`) and graceful fallback is verified,
but outbound calls were not exercised from the build sandbox (network-restricted).
Run on a connected machine to see live data populate.

## What's implemented vs. extension points

**Done and runnable:** provider abstraction with offline fallback; MCP adapter
pattern + TTL cache + shared HTTP helper (timeout/retry/network-gate);
**live** weather/FX/maps adapters (keyless) and keyed Google/weatherapi/Travelpayouts
paths; deterministic cost engine; all 10 agents; LangGraph graph with parallel
fan-out + async fallback; evaluation/confidence; FastAPI with SSE streaming;
13 tests (deterministic core + live-parser); `.env.example`.

**Not in this spine** (deliberately deferred — say the word and I'll add any of
them): React + Vite frontend, i18n bundles, Docker/compose, persistence schema,
and a real visa data source behind `visa.check`.

> Visa data is a small illustrative ruleset. Visa rules change constantly — the
> evaluation agent marks unverified routes low-confidence by design. Do not ship
> visa output without a real source behind `visa.check`.
"# Travel-agent" 
