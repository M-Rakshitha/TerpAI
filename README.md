# CampusPilot: Your AI Campus Assistant

CampusPilot is a multi-agent AI assistant that helps college students navigate campus life by answering plain English questions about dining, navigation, events, study spots, finances, and research — all in one place, in seconds.

---

## 💡 Inspiration

As a student, getting a simple answer about campus life should not require opening five different portals. What is open for lunch right now? How do I get from one building to another between classes? Where can I find a quiet study spot? We kept running into this friction every single day and decided to build something that made it disappear.

CampusPilot is the assistant we wished we had.

---

## 🚀 What It Does

CampusPilot lets students ask anything about campus in plain English and get back a real, useful answer in seconds. It captures the student's live location from the browser and uses it to ground every response in where they actually are on campus. Under the hood, specialized AI agents run in parallel across different domains and merge their results into one unified response.

The system has three core parts:

**For Students:** A conversational interface where you type your question and watch agents work in real time through a live progress feed, then land on a final results page with maps, routes, and actionable information.

**For the Backend:** A FastAPI planner-router-aggregator pipeline powered by the Gemini API and LangGraph, orchestrating domain-specific agents for dining, navigation, events, finances, and research simultaneously.

**For the Frontend:** A Next.js multi-page experience with WebSocket-driven live agent status updates, interactive maps, route visualizations, and data charts.

---

## ⚙️ How We Built It

**Frontend:** Next.js with a multi-page prompt-to-results flow. WebSocket event streams power live agent stage cards so students can see exactly which agents are running and what they are doing in real time. The results page renders interactive maps, route lines, destination markers, and data charts.

**Backend:** FastAPI with a planner-router-aggregator pipeline. The planner breaks the student's question into subtasks, the router sends each subtask to the right specialized agent, and the aggregator merges all results into one clean response payload. All agents run in parallel powered by the Gemini API and coordinated through LangGraph.

**Location Pipeline:** The browser captures coordinates and sends a normalized location payload to the backend. Every agent that needs location pulls from a shared context object. If location is unavailable, the system falls back gracefully and keeps running rather than stopping.

**Languages:** Python, TypeScript

**Frameworks:** FastAPI, Next.js, LangGraph

**AI:** Gemini API

**Transport:** WebSockets, REST/HTTP

---

## 🧠 Challenges We Ran Into

Building multiple AI agents that work reliably together is genuinely hard. When one agent fails or slows down it can drag everything else down with it. The dining agent in particular would collapse into empty results whenever a live data source timed out. Getting parallel branches to fail gracefully without breaking the whole response took far more iteration than expected.

On the frontend, preventing false completed states while agents were still running required carefully syncing the UI to actual WebSocket lifecycle events. We also learned that students tolerate latency if they can see progress — the live stream was added after watching people assume the app was broken after just a few seconds of silence.

---

## 🏅 Accomplishments We Are Proud Of

The parallel agent architecture works and it is genuinely fast. Watching six agents spin up at once and converge into a single answer felt great when it finally clicked. We are also proud that the system degrades gracefully under partial failure, returning something useful rather than breaking entirely — which took real work on both the backend resilience and the frontend reporting side.

---

## 📚 What We Learned

Designing around failure from day one completely changed how we structured the pipeline and the UI. Partial failure is the expected state in distributed systems, not the exception, and your architecture should reflect that from the start.

---

## 🔮 What Is Next for CampusPilot

More agents are coming. Bus schedules, office hours, financial aid deadlines, and campus alerts are all on the roadmap and the router is already built for them. Further out, we want to add personalized memory so the assistant learns each student's preferences over time, and expand beyond UMD since the core pipeline is already campus-agnostic and most school-specific logic lives inside the individual agents.

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Node.js v18 or higher
- npm or yarn
- Gemini API key

### Setup

Clone the repository:

```bash
git clone https://github.com/samankgupta/TerpAI.git
cd TerpAI
```

Install backend dependencies:

```bash
cd backend
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd ../frontend
npm install
```

### Running the Application

You need to run both the frontend and backend simultaneously.

**Start the backend:**

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Start the frontend:**

```bash
cd frontend
npm run dev
```

App runs on: http://localhost:3000

---

## Project Structure

```
TerpAI/
├── backend/
│   ├── main.py
│   ├── models/schemas.py
│   ├── agents/
│   │   ├── dining_agent.py
│   │   ├── navigator_agent.py
│   │   └── ...
│   └── requirements.txt
├── frontend/
│   ├── app/page.tsx
│   ├── lib/api.ts
│   └── components/ai/
│       ├── AgentsPage.tsx
│       └── ResultsPage.tsx
```
