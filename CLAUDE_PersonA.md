# CLAUDE.md — TerpAI · Person A (Backend + AI)

## Project overview

TerpAI is a multi-agent AI platform for University of Maryland students. It unifies Testudo, ELMS, Handshake, dining, events, and research into a single conversational assistant. The user types a natural language query, a Task Planner agent interprets intent, an Agent Router fires the relevant specialized agents in parallel, and a Result Aggregator combines their outputs into a structured JSON response that the frontend renders as cards.

You are responsible for everything that runs on the server: the FastAPI backend, the LangGraph multi-agent system, Gemini API integration, Auth0 JWT validation, and all individual agents.

---

## Tech stack

- **Runtime**: Python 3.11+
- **Framework**: FastAPI
- **Agent orchestration**: LangGraph
- **AI model**: Google Gemini API (`gemini-3.1-flash-lite` for speed and quality)
- **Auth**: Auth0 (JWT validation via `python-jose`)
- **Deployment**: Railway or Render (backend), environment variables via `.env`
- **Package manager**: pip + `requirements.txt`

---

## Folder structure

```
backend/
├── main.py                  # FastAPI app entry point
├── auth/
│   └── jwt_validator.py     # Auth0 JWT middleware
├── agents/
│   ├── task_planner.py      # Converts user input → task JSON
│   ├── router.py            # Selects + runs agents in parallel
│   ├── aggregator.py        # Combines agent outputs
│   ├── schedule_agent.py
│   ├── dining_agent.py
│   ├── events_agent.py
│   ├── finance_agent.py
│   ├── navigator_agent.py
│   ├── study_resources_agent.py
│   └── jobs_research_agent.py
├── models/
│   └── schemas.py           # Pydantic models for all request/response shapes
├── utils/
│   └── gemini_client.py     # Shared Gemini API wrapper
├── tests/
│   └── test_agents.py
├── .env
└── requirements.txt
```

---

## The one API endpoint Person B depends on

Person B's entire frontend connects to a single endpoint. Get this right first.

```
POST /api/query
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "message": "I have an exam tomorrow and $20 for dinner"
}
```

Response shape (always return this structure — agents not triggered return `null`):

```json
{
  "query": "I have an exam tomorrow and $20 for dinner",
  "agents_used": ["schedule", "dining", "finance"],
  "results": {
    "schedule": {
      "agent": "schedule",
      "study_blocks": [
        {
          "start": "18:00",
          "end": "20:00",
          "subject": "CMSC131",
          "type": "review"
        }
      ],
      "next_deadline": { "title": "CMSC131 Exam", "due": "2024-11-15T09:00:00" }
    },
    "dining": {
      "agent": "dining",
      "options": [
        {
          "name": "South Campus Dining",
          "distance_min": 5,
          "budget_ok": true,
          "hours_open": true,
          "dietary_tags": ["vegan", "halal"]
        }
      ]
    },
    "finance": {
      "agent": "finance",
      "weekly_spent": 47.5,
      "budget_remaining": 20.0,
      "suggestion": "You're on track. $20 covers dinner at most dining halls."
    },
    "navigator": null,
    "events": null,
    "study_resources": null,
    "jobs_research": null
  }
}
```

**Do not change the top-level keys of `results` without telling Person B.** The frontend maps directly to these keys.

---

## Agent JSON output contracts

Each agent must return exactly this shape. Add fields freely inside, but never remove or rename top-level keys.

### Schedule agent

```json
{
  "agent": "schedule",
  "study_blocks": [
    {
      "start": "HH:MM",
      "end": "HH:MM",
      "subject": "string",
      "type": "review|practice|reading"
    }
  ],
  "next_deadline": { "title": "string", "due": "ISO8601" }
}
```

### Dining agent

```json
{
  "agent": "dining",
  "options": [
    {
      "name": "string",
      "distance_min": 0,
      "budget_ok": true,
      "hours_open": true,
      "dietary_tags": []
    }
  ]
}
```

### Events agent

```json
{
  "agent": "events",
  "events": [
    {
      "title": "string",
      "location": "string",
      "start": "ISO8601",
      "free_food": false,
      "tags": []
    }
  ]
}
```

### Finance agent

```json
{
  "agent": "finance",
  "weekly_spent": 0.0,
  "budget_remaining": 0.0,
  "suggestion": "string"
}
```

### Navigator agent

```json
{
  "agent": "navigator",
  "origin": "string",
  "destination": "string",
  "walk_minutes": 0,
  "steps": ["string"],
  "map_url": "string"
}
```

### Study resources agent

```json
{
  "agent": "study_resources",
  "tutoring": [
    {
      "service": "string",
      "subject": "string",
      "schedule": "string",
      "location": "string"
    }
  ],
  "office_hours": [
    {
      "professor": "string",
      "course": "string",
      "time": "string",
      "room": "string"
    }
  ]
}
```

### Jobs + research agent

```json
{
  "agent": "jobs_research",
  "jobs": [
    {
      "title": "string",
      "department": "string",
      "pay": "string",
      "apply_url": "string"
    }
  ],
  "labs": [
    {
      "pi": "string",
      "department": "string",
      "topic": "string",
      "contact": "string"
    }
  ],
  "cold_email": "string"
}
```

---

## Task Planner agent

Takes the user's raw message and returns a structured task list. Use Gemini for this.

```python
TASK_PLANNER_PROMPT = """
You are TerpAI's task planner for University of Maryland students.
Given the user's message, identify which of the following agents should be activated:
schedule, dining, events, finance, navigator, study_resources, jobs_research

Return ONLY valid JSON in this exact format:
{
  "tasks": ["agent_name", ...],
  "priority": "high|medium|low",
  "context": {
    "budget": null or number,
    "deadline_mentioned": true or false,
    "location_mentioned": null or "string"
  }
}

User message: {user_message}
"""
```

---

## Agent Router

After the Task Planner returns its task list, the router fires only the required agents — in parallel using `asyncio.gather`.

```python
async def run_agents(tasks: list[str], context: dict) -> dict:
    agent_map = {
        "schedule": schedule_agent.run,
        "dining": dining_agent.run,
        "events": events_agent.run,
        "finance": finance_agent.run,
        "navigator": navigator_agent.run,
        "study_resources": study_resources_agent.run,
        "jobs_research": jobs_research_agent.run,
    }
    selected = {k: v for k, v in agent_map.items() if k in tasks}
    results = await asyncio.gather(*[fn(context) for fn in selected.values()], return_exceptions=True)
    return dict(zip(selected.keys(), results))
```

---

## Auth0 JWT validation

Every request to `/api/query` must include a valid Bearer token. Validate it using Auth0's JWKS endpoint.

```python
# .env
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_AUDIENCE=https://terpai.api

# jwt_validator.py — validate token on every protected route
# Use python-jose and requests to fetch JWKS and verify signature
```

Fail with `401 Unauthorized` if the token is missing, expired, or invalid. Do not silently pass unauthenticated requests.

---

## Gemini API usage

Use `gemini-3.1-flash-lite` by default.

```python
from google import genai

def call_gemini(prompt: str, model: str = "gemini-3.1-flash-lite") -> str:
  with genai.Client(api_key=os.environ["GEMINI_API_KEY"]) as client:
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text
```

Always wrap Gemini calls in try/except. If Gemini fails, return a graceful fallback — never crash the whole `/api/query` response because one agent errored.

---

## Build order (do these in sequence)

1. `main.py` + `/health` endpoint — confirm server runs
2. `schemas.py` — write all Pydantic models for request/response
3. `jwt_validator.py` — Auth0 middleware working end-to-end
4. `gemini_client.py` — confirm Gemini API calls work
5. Task Planner agent — test with sample messages
6. Agent Router — test parallel execution with stub agents
7. Individual agents in this order: dining → events → finance → schedule → study_resources → navigator → jobs_research
8. Result Aggregator
9. Wire everything into `/api/query`
10. Write `tests/test_agents.py` with at least one test per agent

---

## Environment variables

```
GEMINI_API_KEY=
AUTH0_DOMAIN=
AUTH0_AUDIENCE=
GOOGLE_MAPS_API_KEY=
CAPITAL_ONE_NESSIE_API_KEY=   # optional, for finance agent
PORT=8000
```

---

## Data sources per agent

| Agent           | Data source                                                                 |
| --------------- | --------------------------------------------------------------------------- |
| Dining          | UMD Dining API (`dining.umd.edu`) or scraped menu data                      |
| Events          | UMD Events Calendar RSS feed or `events.umd.edu` scrape                     |
| Navigator       | Google Maps Directions API                                                  |
| Schedule        | Hardcoded exam/deadline logic (no live Testudo API) — user provides context |
| Finance         | Session state or Capital One Nessie sandbox API                             |
| Study resources | UMD Tutoring Center page scrape + hardcoded office hour logic               |
| Jobs + research | Handshake-like mock data + UMD lab directory scrape                         |

---

## Rules

- Never return an HTTP 500 to Person B's frontend. Catch all agent exceptions and return `null` for that agent's key in the results object.
- Always validate response JSON with Pydantic before returning.
- Keep each agent file self-contained — one `async def run(context: dict) -> dict` function per file.
- Do not put business logic in `main.py`. It should only handle routing and middleware.
- Every agent must respond in under 8 seconds. Set timeouts on Gemini calls and external API calls.
- Run `black` and `ruff` before committing.
