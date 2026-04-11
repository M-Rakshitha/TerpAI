import os
import json
import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.agents.aggregator import aggregate
from backend.agents.router import run_agents
from backend.agents.task_planner import run as run_task_planner
from backend.models.schemas import QueryRequest, QueryResponse
from backend.utils.env_loader import load_backend_env

load_backend_env()

app = FastAPI(title="TerpAI Backend", version="0.1.0")

AGENT_WORK_SUMMARY = {
    "schedule": "Building study blocks, deadlines, and time plan",
    "dining": "Searching dining options, menus, and dietary/budget fit",
    "events": "Finding campus and nearby events and rankings",
    "finance": "Analyzing budget and spend guidance",
    "navigator": "Resolving destination and route guidance",
    "study_resources": "Collecting tutoring and office hour resources",
    "jobs_research": "Compiling jobs/research opportunities and outreach",
}

SENSITIVE_CONTEXT_TOKENS = {
    "authorization",
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "cookie",
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_truthy_env(var_name: str, default: str = "false") -> bool:
    value = str(os.getenv(var_name, default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _sanitize_context(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in SENSITIVE_CONTEXT_TOKENS):
                sanitized[str(key)] = "***redacted***"
            else:
                sanitized[str(key)] = _sanitize_context(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_context(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_context(item) for item in value]
    return value

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
) -> QueryResponse:
    response, _ = await _execute_pipeline(
        message=payload.message,
        request_id=None,
        include_context=payload.debug_trace_context or _is_truthy_env("TRACE_INCLUDE_CONTEXT_DEFAULT", "false"),
        emit=None,
    )
    return response


async def _execute_pipeline(
    message: str,
    request_id: str | None,
    include_context: bool,
    emit,
) -> tuple[QueryResponse, list[dict]]:
    try:
        trace: list[dict] = []

        planner_context: dict = {}
        per_agent_context: dict[str, dict] = {}

        def _attach_context(event: dict) -> dict:
            if not include_context:
                return event

            enriched_event = dict(event)
            event_type = str(enriched_event.get("type", ""))
            agent = enriched_event.get("agent")
            if event_type == "planner_status":
                enriched_event["context_snapshot"] = _sanitize_context(planner_context)
            elif isinstance(agent, str) and agent in per_agent_context:
                enriched_event["context_snapshot"] = _sanitize_context(per_agent_context[agent])
            return enriched_event

        async def _progress(event: dict) -> None:
            agent = event.get("agent")
            event_payload = {
                **event,
                "timestamp": _ts(),
            }
            if request_id is not None:
                event_payload["request_id"] = request_id
            enriched = _attach_context(
                {
                    **event_payload,
                }
            )
            if isinstance(agent, str) and agent in AGENT_WORK_SUMMARY:
                enriched["work"] = AGENT_WORK_SUMMARY[agent]
            trace.append(enriched)
            if emit is not None:
                await emit(enriched)

        planner_start = {"type": "planner_status", "status": "running", "timestamp": _ts(), "work": "Determining active agents from user query"}
        if request_id is not None:
            planner_start["request_id"] = request_id
        planner_start = _attach_context(planner_start)
        trace.append(planner_start)
        if emit is not None:
            await emit(planner_start)

        plan = await run_task_planner(message)
        context = plan.context.model_dump()
        context["user_message"] = message
        planner_context = dict(context)
        per_agent_context = {agent: dict(context) for agent in plan.tasks}

        planner_done = {
            "type": "planner_status",
            "status": "completed",
            "timestamp": _ts(),
            "tasks": plan.tasks,
            "ai_enrichment_used": bool(context.get("ai_enrichment_used")),
            "ai_routing_used": bool(context.get("ai_routing_used")),
        }
        ai_error = context.get("ai_error")
        if isinstance(ai_error, str) and ai_error:
            planner_done["ai_error"] = ai_error
        if request_id is not None:
            planner_done["request_id"] = request_id
        planner_done = _attach_context(planner_done)
        trace.append(planner_done)
        if emit is not None:
            await emit(planner_done)

        results = await run_agents(plan.tasks, context, progress_callback=_progress)
        return aggregate(message, plan.tasks, results, execution_trace=trace), trace
    except Exception:
        failed = {"type": "pipeline_status", "status": "failed", "timestamp": _ts()}
        if request_id is not None:
            failed["request_id"] = request_id
        trace = [failed]
        if emit is not None:
            await emit(failed)
        return aggregate(message, [], {}, execution_trace=trace), trace


@app.post("/api/query/stream")
async def query_stream(payload: QueryRequest) -> StreamingResponse:
    include_context = payload.debug_trace_context or _is_truthy_env("TRACE_INCLUDE_CONTEXT_DEFAULT", "false")
    request_id = str(uuid4())

    async def _event_generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        await queue.put(
            {
                "type": "query_received",
                "request_id": request_id,
                "timestamp": _ts(),
                "message": payload.message,
            }
        )

        async def _emit_collect(event: dict) -> None:
            await queue.put(event)

        async def _runner() -> None:
            response, _ = await _execute_pipeline(
                message=payload.message,
                request_id=request_id,
                include_context=include_context,
                emit=_emit_collect,
            )
            await queue.put(
                {
                    "type": "query_result",
                    "request_id": request_id,
                    "timestamp": _ts(),
                    "payload": response.model_dump(),
                }
            )
            await queue.put(None)

        task = asyncio.create_task(_runner())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield "data: " + json.dumps(event) + "\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.websocket("/ws/query")
async def ws_query(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            incoming = await websocket.receive_json()
            message = str(incoming.get("message", "")).strip()
            request_id = str(incoming.get("request_id") or uuid4())
            include_context = bool(incoming.get("debug_trace_context")) or _is_truthy_env("TRACE_INCLUDE_CONTEXT_DEFAULT", "false")

            if not message:
                await websocket.send_json(
                    {
                        "type": "query_error",
                        "request_id": request_id,
                        "timestamp": _ts(),
                        "detail": "message is required",
                    }
                )
                continue

            await websocket.send_json(
                {
                    "type": "query_received",
                    "request_id": request_id,
                    "timestamp": _ts(),
                    "message": message,
                }
            )

            try:
                response, _ = await _execute_pipeline(
                    message=message,
                    request_id=request_id,
                    include_context=include_context,
                    emit=lambda event: websocket.send_json(event),
                )

                await websocket.send_json(
                    {
                        "type": "query_result",
                        "request_id": request_id,
                        "timestamp": _ts(),
                        "payload": response.model_dump(),
                    }
                )
            except Exception as exc:
                await websocket.send_json(
                    {
                        "type": "query_error",
                        "request_id": request_id,
                        "timestamp": _ts(),
                        "detail": str(exc),
                    }
                )
    except WebSocketDisconnect:
        return
