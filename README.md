# TerpAI - AI-Powered Student Assistant for UMD

TerpAI is an intelligent multi-agent system powered by LangGraph that helps University of Maryland students with dining, events, finance, scheduling, studying, navigation, and job searches. Each agent is a domain expert that searches web/APIs and provides personalized recommendations.

> **📖 [Full Documentation](docs/INDEX.md)** — Detailed guides for all agents, architecture, and technical details.

## Project Status

| Agent               | Status      | Description                                                                                          | Tests                            |
| ------------------- | ----------- | ---------------------------------------------------------------------------------------------------- | -------------------------------- |
| **Dining**          | ✅ COMPLETE | LangGraph workflow - Campus + off-campus discovery, budget/dietary filtering, route preview          | 7 tests (contract + 6 scenarios) |
| **Events**          | ✅ COMPLETE | LangGraph workflow - Event discovery, preference extraction, intelligent ranking, registration links | 8 scenario tests                 |
| **Finance**         | 🟡 STUB     | Coming next                                                                                          | Contract test only               |
| **Schedule**        | 🟡 STUB     | Coming next                                                                                          | Contract test only               |
| **Study Resources** | 🟡 STUB     | Coming next                                                                                          | Contract test only               |
| **Navigator**       | 🟡 STUB     | Coming next                                                                                          | Contract test only               |
| **Jobs Research**   | 🟡 STUB     | Coming next                                                                                          | Contract test only               |

**Overall:** 2 production-ready agents, 5 planned for upgrade

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend (main.py)                  │
│  Handles: Auth, CORS, API routing, agent orchestration │
└────────────────┬────────────────────────────────────────┘
                 │
      ┌──────────┴──────────┐
      │                     │
   ┌──▼──────────┐    ┌────▼────────────┐
   │Task Planner │    │Route / Executor │
   │(Gemini AI)  │    │(asyncio.gather) │
   └──┬──────────┘    └────▲────────────┘
      │                     │
      └─────────────────────┼────────────────────┐
                            │                    │
          ┌─────────────────┼────────────────────┼──────────┬──────────────┐
          │                 │                    │          │              │
      ┌───▼────┐      ┌────▼────┐      ┌───────▼──┐   ┌───▼────┐   ┌────▼────┐
      │Dining  │      │Events   │      │Finance   │   │Schedule│   │ Etc...  │
      │LangGraph       │LangGraph       │Stub      │   │Stub    │   │         │
      └────────┘      └────────┘      │          │   │        │   │         │
                                       └──────────┘   └────────┘   └─────────┘
                            │
          ┌─────────────────┴──────────────────┐
          │                                    │
      ┌───▼────────────┐            ┌────────▼──────┐
      │Aggregator      │            │Error Handling │
      │(Combine results)            │Fallback Logic │
      └───┬────────────┘            └───────────────┘
          │
      ┌───▼──────────────────┐
      │QueryResponse (JSON)  │
      └──────────────────────┘
```

### Data Flow

1. **Client** sends POST to `/api/query` with `{message: string}`
2. **Auth Middleware** validates Auth0 JWT token
3. **Task Planner** (Gemini) determines which agents to activate
4. **Router** executes selected agents in parallel (8-sec timeout each)
5. **Aggregator** combines results into single response
6. **Client** receives `{query, agents_used, results: {...}}`

---

## Quick Start

### 1. **Clone & Setup Environment**

```bash
cd /Users/samankgupta/Desktop/TerpAI
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. **Configure .env**

Copy template to backend:

```bash
cp backend/.env.template backend/.env
```

Edit `backend/.env` with:

```env
# Server
PORT=8000
CORS_ALLOW_ORIGINS=http://localhost:3000,http://localhost:3001

# Auth0
AUTH0_DOMAIN=your-auth0-domain.auth0.com
AUTH0_AUDIENCE=your-api-identifier
AUTH0_ALGORITHM=RS256

# AI Model
GEMINI_API_KEY=your-gemini-api-key

# Optional: External APIs
UMD_DINING_API_URL=
UMD_DINING_API_KEY=
EVENTBRITE_API_KEY=
GOOGLE_MAPS_API_KEY=
CAPITAL_ONE_NESSIE_API_KEY=

# Geocoding
NOMINATIM_USER_AGENT=terpai-backend/1.0
```

### 3. **Start Backend**

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`

### 4. **Test Endpoints**

```bash
# Health check
curl http://localhost:8000/health

# Query endpoint (requires Auth0 token)
curl -X POST http://localhost:8000/api/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Find a vegan dinner near McKeldin under $15"}'
```

---

## Testing

### **Run All Tests**

```bash
cd /Users/samankgupta/Desktop/TerpAI
source .venv/bin/activate

# All tests
pytest -q backend/tests/

# Just agent contract tests
pytest -q backend/tests/test_agents.py

# Just dining scenario tests
pytest -q backend/tests/agents/test_dining_agent_scenarios.py -v

# Just events scenario tests
pytest -q backend/tests/agents/test_events_agent_scenarios.py -v

# Just task planner tests
pytest -q backend/tests/agents/test_task_planner.py -v

# Combined all
pytest -q backend/tests/
```

### **Direct Agent Invocation (No Backend)**

```bash
# Events agent demo
python test_events_agent_invoke.py

# Task planner demo
python test_task_planner_invoke.py
```

### **Current Test Status**

```
✅ 7 agent contract tests (all agents must return agent + options)
✅ 6 dining scenario tests (location, route, budget, preferences, off-campus, fallback)
✅ 8 events scenario tests (categories, free food, dates, times, links, vague queries)
✅ 15 task planner tests (enrichment, routing, constraints, multi-agent, priorities)
─────────────────────────────────────────────────────────
✅ 36 TOTAL PASSING
```

---

## Project Structure

```
TerpAI/
├── README.md                                  ← You are here
├── docs/                                      ← Full documentation
│   ├── INDEX.md                              ← Documentation index
│   ├── DINING_AGENT_CAPABILITIES.md          ← Dining agent guide
│   ├── EVENTS_AGENT_CAPABILITIES.md          ← Events agent guide
│   └── TASK_PLANNER_DOCUMENTATION.md         ← Task planner guide
├── .env                                       ← Config (gitignored)
├── .gitignore
├── requirements.txt
│
├── backend/
│   ├── main.py                                ← FastAPI entrypoint
│   ├── requirements.txt
│   ├── .env.template
│   │
│   ├── auth/
│   │   └── jwt_validator.py                   ← Auth0 JWT validation
│   │
│   ├── models/
│   │   └── schemas.py                         ← Pydantic schemas
│   │       ├── QueryRequest
│   │       ├── QueryResponse
│   │       ├── DiningResult
│   │       ├── EventsResult
│   │       └── 5 more stub results
│   │
│   ├── agents/
│   │   ├── dining_agent.py                    ← ✅ COMPLETE (LangGraph)
│   │   ├── events_agent.py                    ← ✅ COMPLETE (LangGraph)
│   │   ├── finance_agent.py                   ← 🟡 Stub
│   │   ├── schedule_agent.py                  ← 🟡 Stub
│   │   ├── study_resources_agent.py           ← 🟡 Stub
│   │   ├── navigator_agent.py                 ← 🟡 Stub
│   │   ├── jobs_research_agent.py             ← 🟡 Stub
│   │   ├── task_planner.py                    ← Task router (Gemini)
│   │   ├── router.py                          ← Parallel executor
│   │   └── aggregator.py                      ← Result combiner
│   │
│   ├── utils/
│   │   └── gemini_client.py                   ← Gemini API wrapper
│   │
│   └── tests/
│       ├── test_agents.py                     ← Contract tests (all agents)
│       └── agents/
│           ├── test_dining_agent_scenarios.py ← 6 dining scenarios
│           └── test_events_agent_scenarios.py ← 8 events scenarios
│
├── frontend/                                   ← Coming soon (Next.js)
│   ├── src/
│   │   ├── app/
│   │   │   ├── globals.css
│   │   │   └── page.tsx
│   │   ├── components/
│   │   │   ├── QueryInput.tsx
│   │   │   └── AgentResults.tsx
│   │   └── lib/
│   │       └── api.ts
│   └── package.json
│
├── test_dining_agent_invoke.py                 ← Direct dining demo
└── test_events_agent_invoke.py                 ← Direct events demo
**📖 Full Documentation:** See [docs/TASK_PLANNER_DOCUMENTATION.md](docs/TASK_PLANNER_DOCUMENTATION.md)
```

---

## API Contracts

### **POST /api/query** (Protected by Auth0)

**Request:**

```json
{
  "message": "Find vegan dinner near McKeldin under $15"
}
```

**Response (200 OK):**

```json
{
  "query": "Find vegan dinner near McKeldin under $15",
  "agents_used": ["dining"],
  "results": {
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
      ],
      "menu_recommendations": [
        {
          "name": "South Campus Dining",
          "menu_highlights": ["salad", "rice bowls"],
          "estimated_meal_price": 12.0,
          "source": "campus"
        }
      ],
      "recommendation_basis": {
        "budget": 15.0,
        "dietary_preferences": ["vegan"],
        "menu_preferences": ["dinner"]
      },
      "route_preview": {
        "origin": "McKeldin Library, University of Maryland",
        "destination": "South Campus Dining",
        "map_url": "https://www.google.com/maps/dir/?api=1&..."
      }
    },
    "events": null,
    "schedule": null,
    "finance": null,
    "navigator": null,
    "study_resources": null,
    "jobs_research": null
  }
}
```

---

## 🧠 Task Planner - The Orchestrator

The **Task Planner** is the intelligent backbone that routes requests to agents. It performs three critical functions:

### 1. **Message Enrichment**

Rewrites user queries into detailed, explicit format:

- Input: "Find food under $15"
- Output: "Student needs: Find food under $15 | Budget constraint: under $15"

### 2. **Agent Routing**

Intelligently selects which agents to activate (can run multiple in parallel):

- Query: "Find event tomorrow with free food"
- Route: `["events", "dining"]` → Both run simultaneously

### 3. **Context Extraction**

Extracts actionable constraints for agents:

```python
{
  "budget": 15.0,              # From "$15"
  "deadline_mentioned": true,   # From "tomorrow"
  "location_mentioned": "McKeldin",  # From "near McKeldin"
  "priority": "high"            # Priority level
}
```

### Task Planner Examples

| Query                                     | Extracted Context            | Activated Agents           | Priority |
| ----------------------------------------- | ---------------------------- | -------------------------- | -------- |
| "Find vegan food under $15"               | budget: 15, dietary: vegan   | dining                     | medium   |
| "Exam tomorrow! Need tutoring"            | deadline: true               | schedule, study_resources  | **high** |
| "Events near Engineering building"        | location: Engineering        | events, navigator          | medium   |
| "Check budget, find food, get directions" | budget: null, location: null | finance, dining, navigator | medium   |

### Performance

- Message enrichment: ~1-2 seconds (Gemini LLM)
- Agent routing: ~0.1 seconds (keyword matching)
- **Fallback:** If Gemini fails, uses keyword patterns (instant)

**📖 Full Documentation:** See [TASK_PLANNER_DOCUMENTATION.md](TASK_PLANNER_DOCUMENTATION.md)

---

## Agent Capabilities Summary

### 🍽️ **Dining Agent** (✅ Complete)

- **Discover:** UMD dining halls + nearby restaurants (Overpass)
- **Filter:** Budget, dietary restrictions, menu preferences
- **Rank:** 6-factor weighted scoring
- **Route:** Google Maps walking directions
- **Tests:** 7 (contract + 6 scenarios)

**Example Query:** "Find halal dinner under $20 near McKeldin"

For detailed capabilities, see [docs/DINING_AGENT_CAPABILITIES.md](docs/DINING_AGENT_CAPABILITIES.md)

### 📅 **Events Agent** (✅ Complete)

- **Discover:** UMD calendar + Eventbrite nearby events
- **Filter:** Event types, dates, times, free food
- **Rank:** 6-factor weighted scoring
- **Links:** Auto-generate registration URLs
- **Tests:** 8 scenarios

**Example Query:** "What career events are there this weekend with free food?"

For detailed capabilities, see [docs/EVENTS_AGENT_CAPABILITIES.md](docs/EVENTS_AGENT_CAPABILITIES.md)

### 💰 **Finance Agent** (🟡 Planned)

- Will integrate Capital One Nessie API
- Track spending, budgets, savings goals
- Analyze financial patterns

**Example Query:** "How much did I spend on food this month?"

### 📚 **Schedule Agent** (🟡 Planned)

- Will integrate UMD Testudo API
- Course schedule, exam dates, deadlines
- Conflict detection

**Example Query:** "When do I have exams?"

### 🎓 **Study Resources Agent** (🟡 Planned)

- Tutoring services, office hours, study groups
- Q&A resources (StackOverflow, Piazza)

**Example Query:** "Where can I get help with CS algorithms?"

### 🗺️ **Navigator Agent** (🟡 Planned)

- Campus building coordinates, walking routes
- Transit information, parking

**Example Query:** "How do I get to Engineering building?"

### 💼 **Jobs Research Agent** (🟡 Planned)

- Lab research opportunities, Handshake jobs
- Cold email templates, interview prep

**Example Query:** "What research labs are hiring?"

---

## Environment Variables Reference

| Variable                     | Required | Example                      | Purpose                |
| ---------------------------- | -------- | ---------------------------- | ---------------------- |
| `PORT`                       | Yes      | `8000`                       | Backend port           |
| `CORS_ALLOW_ORIGINS`         | Yes      | `http://localhost:3000`      | Frontend URLs          |
| `AUTH0_DOMAIN`               | Yes      | `tenantname.auth0.com`       | Auth0 tenant           |
| `AUTH0_AUDIENCE`             | Yes      | `https://api.terpai.com`     | Auth0 API ID           |
| `GEMINI_API_KEY`             | Yes      | `AIza...`                    | Google Gemini API      |
| `UMD_DINING_API_URL`         | No       | `https://api.umd.edu/dining` | UMD dining endpoint    |
| `UMD_DINING_API_KEY`         | No       | `token123`                   | UMD dining auth        |
| `EVENTBRITE_API_KEY`         | No       | `event123`                   | Eventbrite search      |
| `GOOGLE_MAPS_API_KEY`        | No       | `AIza...`                    | Google Maps directions |
| `CAPITAL_ONE_NESSIE_API_KEY` | No       | `nessie123`                  | Finance data           |
| `NOMINATIM_USER_AGENT`       | No       | `terpai/1.0`                 | OpenStreetMap agent    |

---

## Dependencies

| Package               | Version      | Purpose             |
| --------------------- | ------------ | ------------------- |
| `fastapi`             | 0.111+       | Web framework       |
| `uvicorn`             | 0.27+        | ASGI server         |
| `langgraph`           | 0.6.11+      | Agent orchestration |
| `langchain-core`      | (transitive) | LLM abstractions    |
| `pydantic`            | 2.0+         | Data validation     |
| `python-jose`         | 3.3.0+       | JWT validation      |
| `google-generativeai` | 0.3+         | Gemini API          |
| `requests`            | 2.31+        | HTTP client         |
| `pytest`              | 8.4+         | Testing framework   |
| `pytest-asyncio`      | 0.24+        | Async test support  |

**Install:** `pip install -r backend/requirements.txt`

---

## Development Workflow

### **Adding a New Agent**

1. **Create agent file** → `backend/agents/{agent_name}_agent.py`
2. **Implement LangGraph workflow** (6 nodes pattern like dining/events)
3. **Add to task planner keywords** → `backend/agents/task_planner.py`
4. **Register router** → `backend/agents/router.py`
5. **Update schemas** → `backend/models/schemas.py`
6. **Write tests** → `backend/tests/agents/test_{agent_name}_agent_scenarios.py`
7. **Update README** → This file

### **Testing Locally**

```bash
# Test single agent
python test_{agent_name}_agent_invoke.py

# Test all agents
pytest -q backend/tests/

# Test with backend running
curl -X POST http://localhost:8000/api/query \
  -H "Authorization: Bearer test_token" \
  -H "Content-Type: application/json" \
  -d '{"message": "Your query here"}'
```

---

## Key Design Patterns

### **LangGraph Workflows**

Each agent uses deterministic 6-node pipelines:

1. `ingest_context` - Extract preferences from message
2. `fetch_*_data` - Gather from APIs/fallbacks
3. `rank_options` - Score and sort by relevance
4. `build_links/metadata` - Generate resources
5. `build_result` - Assemble response
6. `return END` - Compile final output

**Benefits:** Deterministic, testable, graceful fallback, clear state tracking

### **Weighted Ranking**

All agents score options independently, then sort descending:

- Category/type match (highest)
- User preferences (medium)
- Availability/proximity (lower)
- Source quality (slight boost)

### **Graceful Fallback**

If external APIs fail:

1. Try LangGraph `async/await` with 8-sec timeout
2. Fall back to synchronous node execution
3. If both fail, return known entities (fallback DB)
4. Never crash; always return valid response

### **Mocked Testing**

All external calls (APIs, geocoding, search) are mocked with deterministic fixtures:

- No network calls during test
- Repeat tests produce identical results
- Fast (< 1 sec per test)

---

## Troubleshooting

### **Tests Failing with Import Error**

Solution: Ensure `sys.path.append(str(Path(__file__).resolve().parents[3]))` in test files

### **Backend Won't Start**

1. Check `.env` exists and has required keys
2. Verify port 8000 is available: `lsof -i :8000`
3. Ensure venv activated: `source .venv/bin/activate`

### **Auth0 Validation Failing**

1. Verify `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` in `.env`
2. Ensure JWT token is valid and not expired
3. Check CORS origin is in `CORS_ALLOW_ORIGINS`

### **External APIs Timing Out**

1. Set `UMD_DINING_API_KEY=""` to skip external calls (uses fallback)
2. Increase timeout in agent: `timeout=12` in `run()` function
3. Check internet connectivity

---

## What's Next

**Immediate (This Week):**

- [ ] Upgrade Finance agent (Capital One Nessie API)
- [ ] Upgrade Schedule agent (UMD Testudo API)
- [ ] Create scenario tests for both

**Next (This Month):**

- [ ] Upgrade Study Resources agent
- [ ] Upgrade Navigator agent
- [ ] Upgrade Jobs Research agent
- [ ] Frontend implementation (Next.js + Auth0 UI)

**Future:**

- [ ] Deploy to Azure Container Apps
- [ ] Add more data sources (Handshake, LinkedIn APIs)
- [ ] Implement caching layer for frequent queries
- [ ] Add user preference persistence
- [ ] Analytics dashboard

---

## Contributing

1. Create a feature branch: `git checkout -b feature/agent-name`
2. Implement agent following LangGraph 6-node pattern
3. Write 6-8 scenario tests (all must pass)
4. Update this README with agent capabilities
5. Create pull request

---

## License

(Add license info here when decided)

---

## Support

- **Issues:** [GitHub Issues](https://github.com/your-repo)
- **Email:** support@terpai.com
- **Slack:** #terpai-dev

---

**Last Updated:** April 11, 2026  
**Current Version:** 1.0 (2 agents complete, 5 planned)
