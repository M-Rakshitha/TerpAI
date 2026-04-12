# CLAUDE.md - TerpAI Combined Project Summary

## Project Purpose

TerpAI is a multi-agent assistant for UMD students that answers campus questions across dining, navigation, schedule, events, study resources, finance, and job/research domains.

## Current Architecture

- Backend: FastAPI plus planner/router/aggregator pipeline
- Agent orchestration: parallel execution with recovery passes
- Frontend: Next.js app with prompt, live progress, and final visual report pages
- Transport: websocket-first progress plus HTTP fallback response

## Key Work Completed

### Backend core

- Hardened task planning and agent routing pipeline.
- Added typed request contract support for browser coordinates.
- Unified location normalization across HTTP/stream/websocket entry points.
- Enforced non-blocking fallback behavior for missing location.

### Location end-to-end

- Browser captures coordinates and sends location payload.
- Backend receives and normalizes into shared context.
- Navigator uses actual coordinate origin when available.
- If location is missing, backend continues with UMD fallback rather than stopping.

### Dining reliability

- Improved resilience under partial source failures.
- Prevented total empty fallback due slow web branch.
- Kept no-results responses graceful when all live sources truly fail.
- Restored budget-sensitive option behavior for low-budget prompts.

### Frontend UX

- Upgraded live simulation page with status/progress details from stream events.
- Improved final results page with charts, filtered highlights, and interactive map.
- Corrected completion messaging to avoid false success states.

## Important Behavioral Contract

- Location-sensitive queries should not hard-stop the pipeline.
- Real coordinates should be preferred when available.
- UMD fallback should be used when location is unavailable.
- Final payload should remain render-safe even if some agents are partial.

## Main Files of Record

- `backend/main.py`
- `backend/models/schemas.py`
- `backend/agents/dining_agent.py`
- `backend/agents/navigator_agent.py`
- `frontend/app/page.tsx`
- `frontend/lib/api.ts`
- `frontend/components/ai/AgentsPage.tsx`
- `frontend/components/ai/ResultsPage.tsx`
