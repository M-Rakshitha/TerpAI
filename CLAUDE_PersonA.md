# CLAUDE.md - TerpAI - Person A (Backend and AI)

## Scope

Person A owns backend architecture, orchestration, data contracts, and runtime reliability for all agents.

## What We Implemented

### 1) Multi-agent orchestration and execution stability

- Hardened planner -> router -> aggregator flow.
- Preserved per-agent execution status and reduced false completed states for failed outputs.
- Added better recovery paths for weak or partial outputs.

### 2) Location pipeline contract (backend side)

- Query schema now accepts typed location payload:
  - `location: { lat: float, lng: float } | None`
- Added normalized location handling in API pipeline:
  - accepts `location`, legacy `current_location_coords`, or coordinate string
  - stores normalized context under `context["location"]`
  - forwards coordinate origin to navigator context
- Updated HTTP, stream, and websocket paths to forward location consistently.

### 3) Location fallback behavior (non-blocking)

- Removed stopping behavior when location is missing.
- Backend now continues with fallback location (`University of Maryland, College Park`) instead of pausing.
- Emits fallback-applied events for traceability.

### 4) Navigator origin correctness

- Navigator prioritizes real coordinates from `context["location"]`.
- Route origin and map URL origin now use actual coordinates when available.
- Added regression coverage for location object origin behavior.

### 5) Dining agent reliability hardening

- Fixed compatibility for campus source return shapes.
- Added exception-safe parallel branch handling so one source failure does not collapse dining output.
- Made web enrichment opportunistic (non-blocking) to avoid empty fallbacks due to slow web scraping.
- Added campus baseline pricing (`estimated_meal_price`) and `budget_ok` evaluation.
- Preserved soft no-results behavior when all live sources are truly empty.

## Backend Files Touched

- `backend/main.py`
- `backend/models/schemas.py`
- `backend/agents/navigator_agent.py`
- `backend/agents/dining_agent.py`
- `backend/tests/agents/test_multi_agent_integration.py`
- `backend/tests/agents/test_navigator_agent_scenarios.py`
- `backend/tests/agents/test_dining_agent_scenarios.py`

## Backend Guarantees

- Nearby/location-sensitive queries do not block waiting for user input.
- If location exists, navigator origin uses real coordinates.
- If location is missing, fallback routing still completes and agents run.
- Dining returns resilient user-facing results despite partial source failures.
