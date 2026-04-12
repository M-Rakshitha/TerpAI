# CLAUDE.md - TerpAI - Person B (Frontend and UX)

## Scope

Person B owns frontend UX, state transitions, streaming progress visualization, and API payload correctness from browser to backend.

## What We Implemented

### 1) Multi-page interactive experience

- Structured the app into prompt -> live agents -> results flow.
- Improved progression UX so users can see staged execution and final report separately.

### 2) Live execution updates

- Wired websocket event stream updates into UI stage cards.
- Added richer stage fields (`progress`, `currentStep`, `totalSteps`, `activity`, timestamps).
- Improved visual status signaling in agent cards.

### 3) Results experience upgrades

- Implemented richer visual reporting with charts and route context.
- Added interactive map rendering with destination markers and route lines.
- Reduced noisy failure text in final report and focused on useful metrics and takeaways.

### 4) Location payload and browser capture fixes

- Frontend now sends normalized location payload to backend:
  - `location: { lat, lng }`
- Maintains compatibility fields:
  - `user_location`
  - `current_location_coords`
  - `location_permission_granted`
- Added browser location caching and warmup logic.
- Increased geolocation timeouts and maximumAge to reduce false missing locations.

### 5) Correct completion messaging

- UI no longer reports completion when backend returns waiting or paused response.
- Status label reflects actual runtime state instead of false final completion.

## Frontend Files Touched

- `frontend/app/page.tsx`
- `frontend/lib/api.ts`
- `frontend/components/ai/AgentsPage.tsx`
- `frontend/components/ai/ResultsPage.tsx`

## Frontend Guarantees

- Requests carry explicit location object when available.
- Streaming stage UI reflects real agent lifecycle.
- Final report emphasizes actionable content over internal diagnostics.
- Map and route visuals are interactive and user-facing.
