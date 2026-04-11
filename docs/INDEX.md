# TerpAI Documentation Index

Complete documentation for the TerpAI - AI-Powered Student Assistant for UMD.

## Quick Links

### 📋 Agent Documentation

- [**Task Planner Documentation**](TASK_PLANNER_DOCUMENTATION.md) - The orchestrator that routes requests to agents
- [**Events Agent Capabilities**](EVENTS_AGENT_CAPABILITIES.md) - Event discovery, preference extraction, intelligent ranking
- [**Dining Agent Capabilities**](DINING_AGENT_CAPABILITIES.md) - Dining discovery, budget filtering, route preview

### 🏗️ Architecture

- Task Planner: Enriches queries → Routes to agents → Extracts constraints
- Domain Agents: Specialized LangGraph workflows with 6-node pattern
- Router: Parallel agent execution (all agents run simultaneously)
- Aggregator: Combines all results into unified response

### 🔧 Development

- All tests located in: `backend/tests/`
  - Contract tests: `backend/tests/test_agents.py`
  - Scenario tests: `backend/tests/agents/test_*.py`
- All agent implementations: `backend/agents/`
- All utilities: `backend/utils/`

### 📊 Test Coverage

- ✅ 36 total tests (all passing)
  - 7 contract tests (agent API contracts)
  - 6 dining scenario tests
  - 8 events scenario tests
  - 15 task planner tests

### 🚀 Next Steps

1. Upgrade Finance Agent (Capital One Nessie API)
2. Upgrade Schedule Agent (UMD Testudo API)
3. Upgrade remaining agents
4. Frontend implementation (Next.js)

---

**Project Status:** 2 production-ready agents (Dining, Events) + Task Planner orchestrator  
**Model:** Gemini 3.1 Flash Lite  
**Framework:** FastAPI + LangGraph + Pydantic  
**Last Updated:** April 11, 2026
