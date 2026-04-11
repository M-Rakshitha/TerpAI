import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.aggregator import aggregate
from backend.agents.router import run_agents
from backend.agents.task_planner import run as run_task_planner
from backend.auth.jwt_validator import require_auth
from backend.models.schemas import QueryRequest, QueryResponse

app = FastAPI(title="TerpAI Backend", version="0.1.0")

raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
allow_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/query", response_model=QueryResponse)
async def query(
    payload: QueryRequest,
    _token_payload: dict = Depends(require_auth),
) -> QueryResponse:
    try:
        plan = await run_task_planner(payload.message)
        context = plan.context.model_dump()
        context["user_message"] = payload.message
        results = await run_agents(plan.tasks, context)
        return aggregate(payload.message, plan.tasks, results)
    except Exception:
        return aggregate(payload.message, [], {})
