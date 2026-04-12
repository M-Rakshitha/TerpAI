# TerpAI

TerpAI is a multi-agent UMD student assistant with a FastAPI backend and Next.js frontend.
It handles dining, navigation, events, schedule, study resources, finance, and jobs/research workflows through a planner-router-aggregator architecture.

## What Exists Today
- Planner-driven multi-agent execution pipeline
- Websocket-first live progress events
- Aggregated final JSON response for dashboard rendering
- Location-aware query flow with coordinate support
- Dining and navigator reliability fixes for partial failures and fallback behavior
- Visual results UI with charts and interactive map

## Recent Improvements Implemented

### 1) Location End-to-End Reliability
- Frontend sends explicit location object: `{ lat, lng }`
- Backend accepts and normalizes location payload in all entry paths
- Navigator uses real coordinate origin when available
- Missing location no longer blocks query execution; backend falls back to UMD default and continues

### 2) Dining Agent Hardening
- Defensive handling for source branch failures
- Non-blocking web enrichment path to avoid empty results due slow scraping
- Better fallback behavior and budget-sensitive option scoring

### 3) Frontend UX + Progress
- Improved live agent stage progress rendering from websocket events
- Better final results presentation with focused insights
- Interactive route/destination map integration
- Corrected completion status messaging for paused/fallback flows

## High-Level Architecture

```text
Frontend (Next.js)
  -> submit query + optional location
  -> websocket progress stream
  -> final aggregated dashboard

Backend (FastAPI)
  -> Task Planner
  -> Agent Router (parallel)
  -> Agent Recovery / Verification passes
  -> Aggregator
  -> QueryResponse
```

## Repository Structure

```text
backend/
  main.py
  models/schemas.py
  agents/
    dining_agent.py
    navigator_agent.py
    task_planner.py
    router.py
    aggregator.py
  tests/

frontend/
  app/page.tsx
  lib/api.ts
  components/ai/
```

## Run Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

## Test

```bash
cd /Users/samankgupta/Desktop/TerpAI
source .venv/bin/activate
pytest -q backend/tests/
```

## Notes
- If browser location is unavailable, TerpAI should still return results using UMD fallback.
- For location-sensitive prompts, real GPS coordinates are preferred when provided.
