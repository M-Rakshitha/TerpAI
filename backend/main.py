import os
import json
import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.agents.aggregator import aggregate
from backend.agents.router import run_agents
from backend.agents.task_planner import run as run_task_planner
from backend.models.schemas import QueryRequest, QueryResponse
from backend.utils.env_loader import load_backend_env
from backend.utils.ai_workflow import call_gemini_with_retry

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
    "aggregator": "Combining agent outputs into the final summary",
}

AGENT_RESEARCH_FOCUS = {
    "schedule": "Extract deadlines, class timing, and a practical study timeline. Focus only on scheduling outcomes.",
    "dining": "Find concrete dinner options near the user location and validate price fit to constraints.",
    "events": "Find upcoming relevant events and provide date/time/location specifics and registration links.",
    "finance": "Analyze spending feasibility for the stated constraints and produce budget guidance only.",
    "navigator": "Resolve origin/destination and generate practical route directions with map links.",
    "study_resources": "Find tutoring/office-hour/help resources relevant to the user's academic need.",
    "jobs_research": "Find actionable jobs/research opportunities and concrete next steps for outreach.",
}

AGENT_SUBTASKS = {
    "schedule": [
        "Extract deadlines and fixed time constraints",
        "Generate an achievable schedule with priorities",
        "Return a concise execution checklist",
    ],
    "dining": [
        "Find nearby places around the user location",
        "Collect menu/price evidence from web sources",
        "Filter and rank options by budget and constraints",
        "Extract concrete under-budget menu items from source pages",
        "Prepare map-ready route options to top picks",
    ],
    "events": [
        "Find upcoming relevant events",
        "Collect date/time/location and registration links",
        "Rank events by relevance to the request",
    ],
    "finance": [
        "Estimate realistic category costs",
        "Compare estimates against user budget constraints",
        "Provide actionable budget guidance",
    ],
    "navigator": [
        "Resolve precise destination from the request",
        "Generate route details and map links",
        "Provide practical travel notes",
    ],
    "study_resources": [
        "Find tutoring and office-hour resources",
        "Collect links and logistics details",
        "Rank by immediate usefulness",
    ],
    "jobs_research": [
        "Find relevant openings/opportunities",
        "Collect application/outreach details",
        "Produce concrete next actions",
    ],
}


def _fallback_agent_subtasks(agent: str) -> list[str]:
    return list(AGENT_SUBTASKS.get(agent, ["Gather required inputs", "Run analysis", "Finalize response"]))


def _sanitize_agent_subtasks(agent: str, tasks: list[str]) -> list[str]:
    cleaned = [str(item).strip() for item in tasks if str(item).strip()]
    if not cleaned:
        return _fallback_agent_subtasks(agent)

    text_blob = " ".join(cleaned).lower()
    # Keep navigator focused on route/origin/destination and avoid long web research loops.
    if agent == "navigator":
        navigator_terms = ["route", "map", "origin", "destination", "direction", "walk", "travel", "building"]
        if not any(term in text_blob for term in navigator_terms):
            return _fallback_agent_subtasks(agent)
        return cleaned[:3]

    # Dining can use deeper web steps, but must stay dining/menu focused.
    if agent == "dining":
        dining_terms = ["dining", "restaurant", "menu", "price", "budget", "meal", "food"]
        if not any(term in text_blob for term in dining_terms):
            return _fallback_agent_subtasks(agent)
        return cleaned[:5]

    return cleaned


async def _generate_agent_subtasks(
    *,
    message: str,
    enriched_query: str | None,
    agent: str,
    context: dict[str, Any],
) -> list[str]:
    prompt = (
        "You generate execution subtasks for one agent in a multi-agent workflow. "
        "Return ONLY valid JSON as an array of 3 to 7 concise strings. "
        "Each subtask must be action-oriented, specific to this request and this agent, and include live evidence collection where applicable. "
        "For dining/events/jobs_research, include explicit URL or web-source verification steps.\n\n"
        f"Agent: {agent}\n"
        f"Original user request: {message}\n"
        f"Planner enriched request: {enriched_query or message}\n"
        f"Context constraints: {json.dumps({'budget': context.get('budget'), 'location_mentioned': context.get('location_mentioned'), 'deadline_mentioned': context.get('deadline_mentioned')})}\n"
    )
    try:
        raw = await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", timeout_seconds=6, max_attempts=2)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        data = json.loads(cleaned)
        if isinstance(data, list):
            tasks = [str(item).strip() for item in data if str(item).strip()]
            if 3 <= len(tasks) <= 7:
                return _sanitize_agent_subtasks(agent, tasks)
            if len(tasks) > 7:
                return _sanitize_agent_subtasks(agent, tasks[:7])
    except Exception:
        pass
    return _fallback_agent_subtasks(agent)

SENSITIVE_CONTEXT_TOKENS = {
    "authorization",
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "cookie",
}

LOG_DIR = Path(os.getenv("BACKEND_LOG_DIR", Path(__file__).resolve().parent / "logs"))
APP_LOG_FILE = os.getenv("BACKEND_APP_LOG_FILE", "backend.log")
APP_LOG_PATH = LOG_DIR / APP_LOG_FILE


def _configure_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("terpai.backend")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(APP_LOG_PATH, maxBytes=2_000_000, backupCount=5)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = _configure_logging()


async def _persist_event(event: dict, channel: str) -> None:
    return None


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


def _build_agent_prompt(message: str, enriched_query: str | None, agent: str, context: dict[str, Any]) -> str:
    focus = AGENT_RESEARCH_FOCUS.get(agent, "Research only the information relevant to this agent.")
    constraints = {
        "budget": context.get("budget"),
        "location_mentioned": context.get("location_mentioned"),
        "deadline_mentioned": context.get("deadline_mentioned"),
    }
    raw_subtasks = context.get("agent_subtasks")
    if isinstance(raw_subtasks, list):
        subtasks = [str(item).strip() for item in raw_subtasks if str(item).strip()]
    else:
        subtasks = []
    if not subtasks:
        subtasks = AGENT_SUBTASKS.get(agent, ["Research assigned objective", "Return concise result"])
    subtask_text = "\n".join(f"- {task}" for task in subtasks)
    enriched = enriched_query or message
    return (
        f"Original user request: {message}\n"
        f"Planner enriched request: {enriched}\n"
        f"Your assigned agent: {agent}\n"
        f"Research objective: {focus}\n"
        f"Constraints: {constraints}\n"
        "Execute these subtasks in parallel where possible:\n"
        f"{subtask_text}\n"
        "Do not solve other agents' responsibilities. Return only findings relevant to your objective."
    )

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
    request_id = str(uuid4())
    await _persist_event(
        {
            "type": "query_received",
            "request_id": request_id,
            "timestamp": _ts(),
            "message": payload.message,
        },
        channel="http",
    )
    response, _ = await _execute_pipeline(
        message=payload.message,
        request_id=request_id,
        include_context=payload.debug_trace_context or _is_truthy_env("TRACE_INCLUDE_CONTEXT_DEFAULT", "false"),
        emit=None,
    )
    await _persist_event(
        {
            "type": "query_result",
            "request_id": request_id,
            "timestamp": _ts(),
            "payload": response.model_dump(),
        },
        channel="http",
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
            await _persist_event(enriched, channel="pipeline")
            if emit is not None:
                await emit(enriched)

        planner_start = {"type": "planner_status", "status": "running", "timestamp": _ts(), "work": "Determining active agents from user query"}
        if request_id is not None:
            planner_start["request_id"] = request_id
        planner_start = _attach_context(planner_start)
        trace.append(planner_start)
        await _persist_event(planner_start, channel="pipeline")
        if emit is not None:
            await emit(planner_start)

        plan = await run_task_planner(message)
        context = plan.context.model_dump()
        context["user_message"] = message
        planner_context = dict(context)

        dynamic_subtasks = await asyncio.gather(
            *[
                _generate_agent_subtasks(
                    message=message,
                    enriched_query=context.get("enriched_query"),
                    agent=agent,
                    context=context,
                )
                for agent in plan.tasks
            ]
        )
        subtasks_by_agent = {agent: steps for agent, steps in zip(plan.tasks, dynamic_subtasks)}

        per_agent_context = {}
        for agent in plan.tasks:
            scoped_context = dict(context)
            scoped_context["agent_name"] = agent
            scoped_context["agent_subtasks"] = subtasks_by_agent.get(agent, _fallback_agent_subtasks(agent))
            scoped_context["agent_prompt"] = _build_agent_prompt(
                message=message,
                enriched_query=context.get("enriched_query"),
                agent=agent,
                context={**context, "agent_subtasks": scoped_context["agent_subtasks"]},
            )
            per_agent_context[agent] = scoped_context

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
        await _persist_event(planner_done, channel="pipeline")
        if emit is not None:
            await emit(planner_done)

        try:
            agent_timeout_seconds = int(os.getenv("AGENT_TIMEOUT_SECONDS", "90"))
        except (TypeError, ValueError):
            agent_timeout_seconds = 90

        results = await run_agents(
            plan.tasks,
            context,
            context_by_agent=per_agent_context,
            timeout_seconds=max(30, agent_timeout_seconds),
            progress_callback=_progress,
        )

        aggregator_start = {
            "type": "aggregator_status",
            "agent": "aggregator",
            "status": "running",
            "timestamp": _ts(),
            "work": AGENT_WORK_SUMMARY["aggregator"],
        }
        trace.append(aggregator_start)
        await _persist_event(aggregator_start, channel="pipeline")
        if emit is not None:
            await emit(aggregator_start)

        response = aggregate(message, plan.tasks, results, execution_trace=trace)

        aggregator_done = {
            "type": "aggregator_status",
            "agent": "aggregator",
            "status": "completed",
            "timestamp": _ts(),
            "work": AGENT_WORK_SUMMARY["aggregator"],
        }
        trace.append(aggregator_done)
        await _persist_event(aggregator_done, channel="pipeline")
        if emit is not None:
            await emit(aggregator_done)

        return response, trace
    except Exception:
        failed = {"type": "pipeline_status", "status": "failed", "timestamp": _ts()}
        if request_id is not None:
            failed["request_id"] = request_id
        trace = [failed]
        await _persist_event(failed, channel="pipeline")
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
        await _persist_event(
            {
                "type": "query_received",
                "request_id": request_id,
                "timestamp": _ts(),
                "message": payload.message,
            },
            channel="sse",
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
            await _persist_event(
                {
                    "type": "query_result",
                    "request_id": request_id,
                    "timestamp": _ts(),
                    "payload": response.model_dump(),
                },
                channel="sse",
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
            await _persist_event(
                {
                    "type": "query_received",
                    "request_id": request_id,
                    "timestamp": _ts(),
                    "message": message,
                },
                channel="websocket",
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
                await _persist_event(
                    {
                        "type": "query_result",
                        "request_id": request_id,
                        "timestamp": _ts(),
                        "payload": response.model_dump(),
                    },
                    channel="websocket",
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
                await _persist_event(
                    {
                        "type": "query_error",
                        "request_id": request_id,
                        "timestamp": _ts(),
                        "detail": str(exc),
                    },
                    channel="websocket",
                )
    except WebSocketDisconnect:
        return
