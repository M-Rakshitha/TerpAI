import os
import json
import asyncio
import logging
import re
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.agents.aggregator import aggregate
from backend.agents.router import run_agents
from backend.agents.task_planner import run as run_task_planner
from backend.integrations.google_calendar_routes import router as google_calendar_router
from backend.models.schemas import QueryRequest, QueryResponse, TaskPlannerContext, TaskPlannerResponse
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

LOCATION_INTENT_TERMS = {
    "near me",
    "nearby",
    "around me",
    "close by",
    "current location",
    "walking distance",
}

LOG_DIR = Path(os.getenv("BACKEND_LOG_DIR", Path(__file__).resolve().parent / "logs"))
APP_LOG_FILE = os.getenv("BACKEND_APP_LOG_FILE", "backend.log")
APP_LOG_PATH = LOG_DIR / APP_LOG_FILE
RAW_RESPONSE_PATH = Path(
    os.getenv(
        "BACKEND_RAW_RESPONSE_PATH",
        str(LOG_DIR / "latest_query_response.json"),
    )
)
EVENTS_TRACE_PATH = Path(
    os.getenv(
        "BACKEND_EVENTS_TRACE_PATH",
        str(LOG_DIR / "events.jsonl"),
    )
)


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


async def _persist_latest_response(response: QueryResponse) -> None:
    snapshot = response.model_dump(mode="json")

    def _write_snapshot() -> None:
        RAW_RESPONSE_PATH.parent.mkdir(parents=True, exist_ok=True)
        RAW_RESPONSE_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        await asyncio.to_thread(_write_snapshot)
    except Exception as exc:
        LOGGER.warning("Failed to persist latest response snapshot: %s", exc)


async def _persist_latest_events_trace(
    *,
    message: str,
    request_id: str | None,
    trace: list[dict[str, Any]],
    response: QueryResponse,
) -> None:
    payload = {
        "timestamp": _ts(),
        "request_id": request_id,
        "message": message,
        "trace": trace,
        "response": response.model_dump(mode="json"),
    }

    def _write_trace() -> None:
        EVENTS_TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Keep only the latest request trace in events.jsonl by overwriting the file.
        EVENTS_TRACE_PATH.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    try:
        await asyncio.to_thread(_write_trace)
    except Exception as exc:
        LOGGER.warning("Failed to persist latest events trace: %s", exc)


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


def _query_requires_user_location(message: str) -> bool:
    lowered = str(message).lower()
    return any(term in lowered for term in LOCATION_INTENT_TERMS)


def _format_location_coords(value: object) -> str | None:
    if isinstance(value, dict):
        lat = value.get("lat")
        lng = value.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            return f"{lat},{lng}"
        latitude = value.get("latitude")
        longitude = value.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            return f"{latitude},{longitude}"
    if isinstance(value, (list, tuple)) and len(value) == 2:
        latitude, longitude = value
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            return f"{latitude},{longitude}"
    return None


def _normalize_location(value: object) -> dict[str, float] | None:
    if isinstance(value, dict):
        lat = value.get("lat")
        lng = value.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            return {"lat": float(lat), "lng": float(lng)}
        latitude = value.get("latitude")
        longitude = value.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            return {"lat": float(latitude), "lng": float(longitude)}
    if isinstance(value, (list, tuple)) and len(value) == 2:
        lat, lng = value
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            return {"lat": float(lat), "lng": float(lng)}
    if isinstance(value, str) and _looks_like_coordinates(value):
        parts = value.split(",", 1)
        try:
            return {"lat": float(parts[0]), "lng": float(parts[1])}
        except (TypeError, ValueError):
            return None
    return None


def _looks_like_coordinates(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?", value.strip()))


def _build_location_user_input_request(
    default_location: str,
    *,
    prompt: str,
    continuing_with_fallback: bool,
) -> dict[str, Any]:
    return {
        "needs_user_input": True,
        "required_fields": ["user_location"],
        "permission": "location",
        "prompt": prompt,
        "fallback_location": default_location,
        "continuing_with_fallback": continuing_with_fallback,
    }


def _with_user_input_section(
    presentation: dict[str, Any] | None,
    *,
    prompt: str,
    required_fields: list[str],
    permission: str,
    fallback_location: str,
) -> dict[str, Any]:
    payload = dict(presentation or {})
    summary = dict(payload.get("summary") or {})
    sections = list(payload.get("sections") or [])

    highlights = [str(item) for item in summary.get("highlights", []) if str(item).strip()]
    if prompt and prompt not in highlights:
        highlights.insert(0, prompt)
    summary["highlights"] = highlights[:8]

    has_user_input_section = any(str(section.get("id")) == "user_input_request" for section in sections if isinstance(section, dict))
    if not has_user_input_section:
        sections.append(
            {
                "id": "user_input_request",
                "title": "Location Permission",
                "agent": "system",
                "style": "notice",
                "items": [
                    {
                        "prompt": prompt,
                        "required_fields": required_fields,
                        "permission": permission,
                        "fallback_location": fallback_location,
                    }
                ],
            }
        )

    payload["summary"] = summary
    payload["sections"] = sections
    return payload


def _extract_dining_option_names(results: dict[str, Any]) -> list[str]:
    dining = results.get("dining")
    if not isinstance(dining, dict):
        return []
    options = dining.get("options")
    if not isinstance(options, list):
        return []
    names: list[str] = []
    for option in options:
        if not isinstance(option, dict):
            continue
        name = str(option.get("name", "")).strip()
        if name:
            names.append(name)
    return names


def _extract_dining_options(results: dict[str, Any]) -> list[dict[str, Any]]:
    dining = results.get("dining")
    if not isinstance(dining, dict):
        return []
    options = dining.get("options")
    if not isinstance(options, list):
        return []
    return [option for option in options if isinstance(option, dict)]


def _extract_navigation_destinations(results: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    def _is_valid_candidate(value: str) -> bool:
        lowered = value.lower()
        if len(value) < 3:
            return False
        banned = [
            "your objective",
            "search results",
            "narrow down",
            "event search",
            "this weekend",
            "there",
            "here",
            "tba",
            "unknown",
        ]
        return not any(token in lowered for token in banned)

    def _candidate_score(value: str) -> int:
        lowered = value.lower()
        score = 0
        if any(token in lowered for token in ["hall", "building", "center", "union", "library", "campus", "college park", "university"]):
            score += 3
        if "," in value:
            score += 1
        if len(value) > 60:
            score -= 2
        return score

    def _append(value: Any) -> None:
        text = str(value or "").strip()
        if text and _is_valid_candidate(text):
            candidates.append(text)

    dining = results.get("dining") if isinstance(results.get("dining"), dict) else {}
    for option in dining.get("options", []) if isinstance(dining.get("options"), list) else []:
        if isinstance(option, dict):
            _append(option.get("name"))

    events = results.get("events") if isinstance(results.get("events"), dict) else {}
    event_items = []
    for key in ("events", "event_recommendations", "options"):
        payload = events.get(key)
        if isinstance(payload, list):
            event_items = payload
            break
    for item in event_items:
        if isinstance(item, dict):
            _append(item.get("location"))
            _append(item.get("venue"))

    study = results.get("study_resources") if isinstance(results.get("study_resources"), dict) else {}
    for key in ("tutoring", "office_hours", "resources"):
        entries = study.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            _append(entry.get("location"))
            _append(entry.get("room"))
            _append(entry.get("name"))

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    deduped.sort(key=_candidate_score, reverse=True)
    return deduped[:8]


def _build_route_map_url(origin: str, destination_name: str, coordinates: list[Any] | None) -> str:
    if isinstance(coordinates, list) and len(coordinates) == 2:
        destination = f"{coordinates[0]},{coordinates[1]}"
    else:
        destination = destination_name
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote_plus(origin or 'current location')}"
        f"&destination={quote_plus(str(destination))}"
        "&travelmode=walking"
    )


def _has_navigator_route_matrix(results: dict[str, Any], dining_names: list[str]) -> bool:
    navigator = results.get("navigator")
    if not isinstance(navigator, dict):
        return False
    routes_by_option = navigator.get("routes_by_option")
    if not isinstance(routes_by_option, list):
        return False

    covered: set[str] = set()
    for route in routes_by_option:
        if not isinstance(route, dict):
            continue
        name = str(route.get("destination") or route.get("name") or "").strip().lower()
        map_url = str(route.get("map_url") or "").strip()
        if name and map_url:
            covered.add(name)

    target = min(3, len(dining_names))
    dining_lower = [name.lower() for name in dining_names[:3]]
    matched = sum(1 for name in dining_lower if name in covered)
    return matched >= target and target > 0


def _enrich_dining_with_route_matrix(results: dict[str, Any]) -> None:
    dining = results.get("dining")
    navigator = results.get("navigator")
    if not isinstance(dining, dict) or not isinstance(navigator, dict):
        return

    options = dining.get("options")
    if not isinstance(options, list):
        return

    routes_by_option = navigator.get("routes_by_option")
    if not isinstance(routes_by_option, list):
        return

    routes_by_name: dict[str, dict[str, Any]] = {}
    for route in routes_by_option:
        if not isinstance(route, dict):
            continue
        name = str(route.get("destination") or route.get("name") or "").strip().lower()
        if name:
            routes_by_name[name] = route

    origin = str(navigator.get("origin") or "current location")
    for option in options:
        if not isinstance(option, dict):
            continue
        name = str(option.get("name") or "").strip()
        if not name:
            continue
        route = routes_by_name.get(name.lower())
        if route and route.get("map_url"):
            option["route_map_url"] = route.get("map_url")
            option["route_walk_minutes"] = route.get("walk_minutes")
            option["route_description"] = route.get("description")
        elif not option.get("route_map_url"):
            coords = option.get("coordinates") if isinstance(option.get("coordinates"), list) else None
            option["route_map_url"] = _build_route_map_url(origin, name, coords)
            option["route_description"] = f"Walk from {origin} to {name}."


def _assess_output_quality(plan_tasks: list[str], results: dict[str, Any]) -> dict[str, Any]:
    gaps: list[str] = []

    dining_options = _extract_dining_options(results)
    dining_names = [str(option.get("name") or "").strip() for option in dining_options if str(option.get("name") or "").strip()]

    if "dining" in plan_tasks and not dining_names:
        gaps.append("missing_dining_options")

    if "navigator" in plan_tasks and dining_names:
        if _is_generic_navigator_payload(results.get("navigator") if isinstance(results.get("navigator"), dict) else None):
            gaps.append("generic_navigation")
        if not _has_navigator_route_matrix(results, dining_names):
            gaps.append("missing_per_option_routes")

    score = max(0, 100 - (25 * len(gaps)))
    return {
        "score": score,
        "gaps": gaps,
        "should_retry": bool(gaps),
    }


def _extract_source_links(payload: dict[str, Any]) -> list[str]:
    links: list[str] = []

    def _visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = str(key).lower()
                if lowered.endswith("url") and isinstance(item, str) and item.startswith(("http://", "https://")):
                    links.append(item)
                else:
                    _visit(item)
            return
        if isinstance(value, list):
            for item in value:
                _visit(item)

    _visit(payload)
    deduped: list[str] = []
    seen: set[str] = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        deduped.append(link)
    return deduped[:20]


def _verify_agent_payload(agent: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    gaps: list[str] = []
    numeric: dict[str, Any] = {}
    links_count = 0

    if not isinstance(payload, dict):
        return {
            "agent": agent,
            "ok": False,
            "score": 0,
            "gaps": ["missing_payload"],
            "should_reinvoke": True,
            "numeric": numeric,
            "links_count": 0,
            "api_first_ok": False,
        }

    if payload.get("error"):
        gaps.append("agent_error")

    links_count = len(_extract_source_links(payload))
    if links_count == 0 and agent in {"dining", "events", "study_resources", "jobs_research"}:
        gaps.append("missing_source_links")

    data_sources = payload.get("data_sources") if isinstance(payload.get("data_sources"), dict) else {}
    api_sources = data_sources.get("api_sources") if isinstance(data_sources.get("api_sources"), list) else []
    api_first_ok = True
    if agent in {"schedule", "study_resources"}:
        expected = {"umdio", "planetterp"}
        api_first_ok = expected.issubset({str(item).lower() for item in api_sources})
        if not api_first_ok:
            gaps.append("api_sources_incomplete")

    if agent == "dining":
        options = payload.get("options") if isinstance(payload.get("options"), list) else []
        numeric["options"] = len(options)
        if not options:
            gaps.append("missing_dining_options")
    elif agent == "navigator":
        steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
        numeric["steps"] = len(steps)
        if not str(payload.get("map_url") or "").strip():
            gaps.append("missing_map_url")
        if not steps:
            gaps.append("missing_steps")
        if _is_generic_navigator_payload(payload):
            gaps.append("generic_navigation")
    elif agent == "events":
        items = payload.get("events") if isinstance(payload.get("events"), list) else payload.get("options") if isinstance(payload.get("options"), list) else []
        numeric["events"] = len(items)
        if not items:
            gaps.append("missing_events")
    elif agent == "schedule":
        blocks = payload.get("study_blocks") if isinstance(payload.get("study_blocks"), list) else []
        numeric["study_blocks"] = len(blocks)
        if not blocks:
            gaps.append("missing_study_blocks")
        if not isinstance(payload.get("next_deadline"), dict):
            gaps.append("missing_next_deadline")
    elif agent == "study_resources":
        tutoring = payload.get("tutoring") if isinstance(payload.get("tutoring"), list) else []
        office_hours = payload.get("office_hours") if isinstance(payload.get("office_hours"), list) else []
        resources = payload.get("resources") if isinstance(payload.get("resources"), list) else []
        numeric["resources_total"] = len(tutoring) + len(office_hours) + len(resources)
        if numeric["resources_total"] <= 0:
            gaps.append("missing_study_resources")
    elif agent == "finance":
        weekly_spent = payload.get("weekly_spent")
        budget_remaining = payload.get("budget_remaining")
        numeric["weekly_spent"] = weekly_spent
        numeric["budget_remaining"] = budget_remaining
        if not isinstance(weekly_spent, (int, float)) or not isinstance(budget_remaining, (int, float)):
            gaps.append("missing_finance_numbers")
        if not str(payload.get("suggestion") or "").strip():
            gaps.append("missing_finance_suggestion")
    elif agent == "jobs_research":
        jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
        labs = payload.get("labs") if isinstance(payload.get("labs"), list) else []
        numeric["jobs"] = len(jobs)
        numeric["labs"] = len(labs)
        if not jobs and not labs:
            gaps.append("missing_opportunities")

    score = max(0, 100 - (18 * len(gaps)))
    return {
        "agent": agent,
        "ok": len(gaps) == 0,
        "score": score,
        "gaps": gaps,
        "should_reinvoke": len(gaps) > 0,
        "numeric": numeric,
        "links_count": links_count,
        "api_first_ok": api_first_ok,
    }


async def _verify_and_reinvoke_agents(
    *,
    plan_tasks: list[str],
    base_context: dict[str, Any],
    per_agent_context: dict[str, dict[str, Any]],
    results: dict[str, Any],
    progress_callback,
    timeout_seconds: int,
    request_id: str | None,
    trace: list[dict[str, Any]],
    emit,
) -> tuple[dict[str, Any], dict[str, Any]]:
    merged = dict(results)
    verification_items: list[dict[str, Any]] = []

    for agent in plan_tasks:
        payload = merged.get(agent) if isinstance(merged.get(agent), dict) else None
        verdict = _verify_agent_payload(agent, payload)
        verification_items.append(verdict)

        if not verdict.get("should_reinvoke"):
            continue

        reinvoke_start = {
            "type": "agent_reinvoke",
            "status": "running",
            "agent": agent,
            "timestamp": _ts(),
            "reason": verdict.get("gaps", []),
        }
        if request_id is not None:
            reinvoke_start["request_id"] = request_id
        trace.append(reinvoke_start)

        scoped_context = dict(per_agent_context.get(agent, {}))
        scoped_context["verification_feedback"] = verdict.get("gaps", [])
        navigator_candidates: list[str] = []
        if agent == "navigator":
            navigator_candidates = _extract_navigation_destinations(merged)
            if navigator_candidates:
                scoped_context["candidate_destinations"] = navigator_candidates
                scoped_context["destination"] = navigator_candidates[0]
        scoped_context["agent_subtasks"] = list(scoped_context.get("agent_subtasks") or _fallback_agent_subtasks(agent)) + [
            "Verify response includes concrete links and numeric details where applicable",
            "Cross-check accuracy against API/web evidence before finalizing",
        ]
        scoped_context["agent_prompt"] = _build_agent_prompt(
            message=str(base_context.get("user_message", "")),
            enriched_query=base_context.get("enriched_query"),
            agent=agent,
            context={**base_context, "agent_subtasks": scoped_context["agent_subtasks"]},
        )

        rerun = {}
        if agent == "navigator" and navigator_candidates:
            for destination in navigator_candidates[:3]:
                nav_context = dict(base_context)
                nav_context["destination"] = destination
                nav_context["candidate_destinations"] = navigator_candidates
                nav_scoped = dict(scoped_context)
                nav_scoped["destination"] = destination
                nav_scoped["candidate_destinations"] = navigator_candidates
                try:
                    rerun = await asyncio.wait_for(
                        run_agents(
                            [agent],
                            nav_context,
                            context_by_agent={agent: nav_scoped},
                            timeout_seconds=max(20, timeout_seconds // 2),
                            progress_callback=progress_callback,
                        ),
                        timeout=max(20, timeout_seconds // 2),
                    )
                except asyncio.TimeoutError:
                    rerun = {}
                payload = rerun.get(agent) if isinstance(rerun.get(agent), dict) else None
                if isinstance(payload, dict) and not _is_generic_navigator_payload(payload):
                    break
        else:
            try:
                rerun = await asyncio.wait_for(
                    run_agents(
                        [agent],
                        base_context,
                        context_by_agent={agent: scoped_context},
                        timeout_seconds=max(20, timeout_seconds // 2),
                        progress_callback=progress_callback,
                    ),
                    timeout=max(20, timeout_seconds // 2),
                )
            except asyncio.TimeoutError:
                rerun = {}

        if isinstance(rerun.get(agent), dict):
            merged[agent] = rerun[agent]

        updated_payload = merged.get(agent) if isinstance(merged.get(agent), dict) else None
        updated_verdict = _verify_agent_payload(agent, updated_payload)
        verification_items.append({**updated_verdict, "after_reinvoke": True})

        reinvoke_done = {
            "type": "agent_reinvoke",
            "status": "completed",
            "agent": agent,
            "timestamp": _ts(),
            "score": updated_verdict.get("score"),
            "remaining_gaps": updated_verdict.get("gaps", []),
        }
        if request_id is not None:
            reinvoke_done["request_id"] = request_id
        trace.append(reinvoke_done)

    overall_score = int(sum(int(item.get("score", 0)) for item in verification_items) / max(1, len(verification_items)))
    verification_summary = {
        "overall_score": overall_score,
        "items": verification_items,
        "needs_attention": [item for item in verification_items if not item.get("ok")],
    }
    return merged, verification_summary


def _is_generic_navigator_payload(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return True
    destination = str(payload.get("destination", "")).lower()
    steps = " ".join(str(item) for item in payload.get("steps", []) if isinstance(item, str)).lower()
    explicit_generic_markers = [
        "vegan restaurants",
        "restaurants near current location",
        "your objective",
        "narrow down",
        "search results",
    ]
    if any(marker in destination or marker in steps for marker in explicit_generic_markers):
        return True

    if not destination.strip() or destination.strip() in {"there", "here", "destination", "the request"}:
        return True

    # 'search for' by itself is acceptable when destination is concrete.
    if "search for" in steps and any(token in destination for token in ["objective", "results", "near me", "current location"]):
        return True

    return False


async def _recover_weak_results(
    *,
    plan_tasks: list[str],
    base_context: dict[str, Any],
    per_agent_context: dict[str, dict[str, Any]],
    results: dict[str, Any],
    progress_callback,
    timeout_seconds: int,
    best_output_pass: bool = False,
) -> dict[str, Any]:
    merged = dict(results)

    if "dining" in plan_tasks:
        dining_names = _extract_dining_option_names(merged)
        if not dining_names:
            allow_seed_fallback = _is_truthy_env("DINING_ALLOW_SEED_FALLBACK", "false")
            recovery_context = dict(base_context)
            recovery_scoped = dict(per_agent_context.get("dining", {}))
            if allow_seed_fallback:
                recovery_context["force_seed_fallback"] = True
                recovery_scoped["force_seed_fallback"] = True
            recovery_scoped["agent_subtasks"] = [
                "Return concrete nearby dining options immediately",
                "If live data is unavailable, use curated local fallback options",
                "Provide route-ready output fields for navigation",
            ]
            recovery_scoped["agent_prompt"] = _build_agent_prompt(
                message=str(base_context.get("user_message", "")),
                enriched_query=base_context.get("enriched_query"),
                agent="dining",
                context={**recovery_context, "agent_subtasks": recovery_scoped["agent_subtasks"]},
            )
            try:
                recovered_dining = await asyncio.wait_for(
                    run_agents(
                        ["dining"],
                        recovery_context,
                        context_by_agent={"dining": recovery_scoped},
                        timeout_seconds=max(20, timeout_seconds // 2),
                        progress_callback=None,
                    ),
                    timeout=max(20, timeout_seconds // 2),
                )
            except asyncio.TimeoutError:
                recovered_dining = {}
            if isinstance(recovered_dining.get("dining"), dict):
                merged["dining"] = recovered_dining["dining"]

    dining_names = _extract_dining_option_names(merged)
    if "navigator" in plan_tasks and _is_generic_navigator_payload(merged.get("navigator") if isinstance(merged.get("navigator"), dict) else None):
        generic_candidates = _extract_navigation_destinations(merged)
        if generic_candidates and not dining_names:
            destination_name = generic_candidates[0]
            nav_context = dict(base_context)
            if not _looks_like_coordinates(nav_context.get("user_location")):
                formatted_coords = _format_location_coords(nav_context.get("current_location_coords"))
                if formatted_coords:
                    nav_context["user_location"] = formatted_coords
            nav_context["destination"] = destination_name
            nav_context["candidate_destinations"] = generic_candidates

            nav_scoped = dict(per_agent_context.get("navigator", {}))
            nav_scoped["destination"] = destination_name
            nav_scoped["candidate_destinations"] = generic_candidates
            nav_scoped["agent_subtasks"] = [
                "Use available agent outputs to select the most concrete destination",
                "Generate precise walking directions to that destination",
                "Return map URL and concise navigation steps",
            ]
            nav_scoped["agent_prompt"] = _build_agent_prompt(
                message=str(base_context.get("user_message", "")),
                enriched_query=base_context.get("enriched_query"),
                agent="navigator",
                context={**nav_context, "agent_subtasks": nav_scoped["agent_subtasks"]},
            )

            try:
                recovered_navigator = await asyncio.wait_for(
                    run_agents(
                        ["navigator"],
                        nav_context,
                        context_by_agent={"navigator": nav_scoped},
                        timeout_seconds=max(20, timeout_seconds // 2),
                        progress_callback=None,
                    ),
                    timeout=max(20, timeout_seconds // 2),
                )
            except asyncio.TimeoutError:
                recovered_navigator = {}
            if isinstance(recovered_navigator.get("navigator"), dict):
                merged["navigator"] = recovered_navigator["navigator"]

    if "navigator" in plan_tasks and dining_names and _is_generic_navigator_payload(merged.get("navigator") if isinstance(merged.get("navigator"), dict) else None):
        destination_name = dining_names[0]
        nav_context = dict(base_context)
        if not _looks_like_coordinates(nav_context.get("user_location")):
            formatted_coords = _format_location_coords(nav_context.get("current_location_coords"))
            if formatted_coords:
                nav_context["user_location"] = formatted_coords
        nav_context["destination"] = destination_name
        nav_context["selected_dining_option"] = destination_name
        nav_context["candidate_destinations"] = dining_names[:5]

        nav_scoped = dict(per_agent_context.get("navigator", {}))
        nav_scoped["destination"] = destination_name
        nav_scoped["selected_dining_option"] = destination_name
        nav_scoped["candidate_destinations"] = dining_names[:5]
        nav_scoped["agent_subtasks"] = [
            "Route from user origin to the selected restaurant",
            "Return turn-by-turn style walking guidance",
            "Include map URL and destination details for the selected restaurant",
        ]
        nav_scoped["agent_prompt"] = _build_agent_prompt(
            message=str(base_context.get("user_message", "")),
            enriched_query=base_context.get("enriched_query"),
            agent="navigator",
            context={**nav_context, "agent_subtasks": nav_scoped["agent_subtasks"]},
        )

        try:
            recovered_navigator = await asyncio.wait_for(
                run_agents(
                    ["navigator"],
                    nav_context,
                    context_by_agent={"navigator": nav_scoped},
                    timeout_seconds=max(20, timeout_seconds // 2),
                    progress_callback=None,
                ),
                timeout=max(20, timeout_seconds // 2),
            )
        except asyncio.TimeoutError:
            recovered_navigator = {}
        if isinstance(recovered_navigator.get("navigator"), dict):
            nav_payload = dict(recovered_navigator["navigator"])
            nav_payload["options"] = dining_names[:5]
            merged["navigator"] = nav_payload

    dining_options = _extract_dining_options(merged)
    dining_names = [str(option.get("name") or "").strip() for option in dining_options if str(option.get("name") or "").strip()]
    if (
        "navigator" in plan_tasks
        and dining_names
        and (best_output_pass or not _has_navigator_route_matrix(merged, dining_names))
    ):
        max_routes = min(3, len(dining_names))
        route_targets = dining_names[:max_routes]

        async def _run_nav_for_destination(destination_name: str) -> dict[str, Any]:
            nav_context = dict(base_context)
            if not _looks_like_coordinates(nav_context.get("user_location")):
                formatted_coords = _format_location_coords(nav_context.get("current_location_coords"))
                if formatted_coords:
                    nav_context["user_location"] = formatted_coords
            nav_context["destination"] = destination_name
            nav_context["selected_dining_option"] = destination_name
            nav_context["candidate_destinations"] = dining_names[:5]

            nav_scoped = dict(per_agent_context.get("navigator", {}))
            nav_scoped["destination"] = destination_name
            nav_scoped["selected_dining_option"] = destination_name
            nav_scoped["candidate_destinations"] = dining_names[:5]
            nav_scoped["agent_subtasks"] = [
                "Route from user origin to the selected restaurant",
                "Return exact walking route details for this destination",
                "Include map URL and walk time for this destination",
            ]
            nav_scoped["agent_prompt"] = _build_agent_prompt(
                message=str(base_context.get("user_message", "")),
                enriched_query=base_context.get("enriched_query"),
                agent="navigator",
                context={**nav_context, "agent_subtasks": nav_scoped["agent_subtasks"]},
            )

            try:
                rerun = await asyncio.wait_for(
                    run_agents(
                        ["navigator"],
                        nav_context,
                        context_by_agent={"navigator": nav_scoped},
                        timeout_seconds=max(18, timeout_seconds // 3),
                        progress_callback=None,
                    ),
                    timeout=max(18, timeout_seconds // 3),
                )
            except asyncio.TimeoutError:
                rerun = {}

            payload = rerun.get("navigator") if isinstance(rerun.get("navigator"), dict) else {}
            origin = str(payload.get("origin") or base_context.get("user_location") or "current location")
            if origin == "current location":
                preferred_origin = _format_location_coords(base_context.get("current_location_coords"))
                if preferred_origin:
                    origin = preferred_origin
            if payload.get("map_url"):
                return {
                    "destination": destination_name,
                    "origin": origin,
                    "walk_minutes": payload.get("walk_minutes"),
                    "steps": payload.get("steps", []),
                    "map_url": payload.get("map_url"),
                    "description": f"Walk from {origin} to {destination_name} in about {payload.get('walk_minutes') or 'unknown'} minutes.",
                    "source": "navigator_rerun",
                }

            option = next((item for item in dining_options if str(item.get("name") or "").strip() == destination_name), None)
            coordinates = option.get("coordinates") if isinstance(option, dict) and isinstance(option.get("coordinates"), list) else None
            return {
                "destination": destination_name,
                "origin": origin,
                "walk_minutes": None,
                "steps": [],
                "map_url": _build_route_map_url(origin, destination_name, coordinates),
                "description": f"Walk from {origin} to {destination_name}; route details were reconstructed from available dining coordinates.",
                "source": "route_fallback",
            }

        route_results = await asyncio.gather(*[_run_nav_for_destination(name) for name in route_targets])
        route_matrix = [item for item in route_results if isinstance(item, dict) and item.get("map_url")]

        navigator_payload = merged.get("navigator") if isinstance(merged.get("navigator"), dict) else {}
        updated_navigator = dict(navigator_payload)
        updated_navigator["options"] = dining_names[:5]
        if route_matrix:
            updated_navigator["routes_by_option"] = route_matrix
            if not updated_navigator.get("map_url"):
                updated_navigator["map_url"] = route_matrix[0].get("map_url")
        merged["navigator"] = updated_navigator

        _enrich_dining_with_route_matrix(merged)

    return merged


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


def _fallback_plan_fast(message: str) -> TaskPlannerResponse:
    lowered = str(message).lower()
    tasks: list[str] = []

    if any(token in lowered for token in [
        "vegan",
        "vegetarian",
        "halal",
        "kosher",
        "gluten",
        "food",
        "dining",
        "restaurant",
        "eat",
        "lunch",
        "dinner",
        "coffee",
        "cafe",
        "dumpling",
        "dumplings",
        "ramen",
        "noodle",
        "noodles",
        "sushi",
        "pizza",
        "taco",
        "burger",
        "boba",
    ]):
        tasks.append("dining")
    if any(token in lowered for token in ["near me", "nearby", "around me", "directions", "route", "navigate", "where is", "walk", "get to", "how do i get to", "library"]):
        tasks.append("navigator")
    if any(token in lowered for token in ["quiet study", "study spot", "study spots", "tutoring", "office hours", "study resources", "academic support"]):
        tasks.append("study_resources")
    if any(token in lowered for token in ["event", "events", "weekend", "workshop", "seminar", "club"]):
        tasks.append("events")
    if any(token in lowered for token in ["register for classes", "register classes", "class registration", "course registration", "how do i register", "enroll"]):
        tasks.append("schedule")

    if not tasks:
        tasks = ["navigator"] if any(token in lowered for token in ["where", "route", "navigate", "direction", "library", "get to", "how do i get to"]) else ["dining"]

    location_mentioned = "current location" if any(token in lowered for token in ["near me", "nearby", "around me", "current location"]) else None
    return TaskPlannerResponse(
        tasks=tasks,
        priority="medium",
        context=TaskPlannerContext(
            budget=None,
            deadline_mentioned=False,
            location_mentioned=location_mentioned,
            enriched_query=message,
            ai_enrichment_used=False,
            ai_routing_used=False,
            ai_error="planner_timeout_fallback",
        ),
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

app.include_router(google_calendar_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/query", response_model=QueryResponse)
async def query(
    payload: QueryRequest,
) -> QueryResponse:
    request_id = str(uuid4())
    response, _ = await _execute_pipeline(
        message=payload.message,
        request_id=request_id,
        include_context=payload.debug_trace_context or _is_truthy_env("TRACE_INCLUDE_CONTEXT_DEFAULT", "false"),
        client_context={
            "location": payload.location.model_dump() if payload.location else None,
            "user_location": payload.user_location,
            "current_location_coords": payload.current_location_coords,
            "location_permission_granted": payload.location_permission_granted,
        },
        emit=None,
    )
    return response


async def _execute_pipeline(
    message: str,
    request_id: str | None,
    include_context: bool,
    client_context: dict[str, Any] | None,
    emit,
) -> tuple[QueryResponse, list[dict]]:
    try:
        trace: list[dict] = []
        client_context = client_context or {}
        normalized_location = _normalize_location(client_context.get("location"))
        if normalized_location is None:
            normalized_location = _normalize_location(client_context.get("current_location_coords"))

        provided_location_raw = client_context.get("user_location")
        provided_location = str(provided_location_raw).strip() if isinstance(provided_location_raw, str) else ""
        provided_coords = _format_location_coords(client_context.get("location")) or _format_location_coords(
            client_context.get("current_location_coords")
        )
        if not provided_coords and _looks_like_coordinates(provided_location):
            provided_coords = provided_location
        if normalized_location is None and provided_coords:
            normalized_location = _normalize_location(provided_coords)
        # Prefer explicit browser coordinates as the route origin whenever available.
        if provided_coords:
            provided_location = provided_coords
        location_permission_granted = client_context.get("location_permission_granted")
        location_request_payload: dict[str, Any] | None = None
        default_location = "University of Maryland, College Park"

        planner_context: dict = {}
        per_agent_context: dict[str, dict] = {}

        if _query_requires_user_location(message) and not provided_location:
            fallback_reason = "location_permission_denied" if location_permission_granted is False else "location_unavailable"
            location_request_payload = _build_location_user_input_request(
                default_location,
                prompt=(
                    "Location was unavailable. "
                    f"Continuing with default location: {default_location}."
                ),
                continuing_with_fallback=True,
            )
            provided_location = default_location
            location_event = {
                "type": "user_input_request",
                "status": "fallback_applied",
                "timestamp": _ts(),
                "reason": fallback_reason,
                "pipeline_paused": False,
                "continuing_with_fallback": True,
                "fallback_location": default_location,
                "location_permission_granted": bool(location_permission_granted) if location_permission_granted is not None else None,
            }
            if request_id is not None:
                location_event["request_id"] = request_id
            trace.append(location_event)
            if emit is not None:
                await emit(location_event)
        elif _query_requires_user_location(message) and provided_location:
            location_event = {
                "type": "user_input_request",
                "status": "provided",
                "timestamp": _ts(),
                "reason": "location_received",
                "pipeline_paused": False,
                "continuing_with_fallback": False,
                "location_permission_granted": bool(location_permission_granted) if location_permission_granted is not None else True,
            }
            if request_id is not None:
                location_event["request_id"] = request_id
            trace.append(location_event)
            if emit is not None:
                await emit(location_event)

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

        try:
            planner_timeout_seconds = int(os.getenv("PLANNER_TIMEOUT_SECONDS", "12"))
        except (TypeError, ValueError):
            planner_timeout_seconds = 12

        try:
            plan = await asyncio.wait_for(run_task_planner(message), timeout=max(4, planner_timeout_seconds))
        except asyncio.TimeoutError:
            plan = _fallback_plan_fast(message)
        except Exception as exc:
            plan = _fallback_plan_fast(message)
            planner_exception_event = {
                "type": "planner_status",
                "status": "fallback",
                "timestamp": _ts(),
                "reason": "planner_exception",
                "error": f"{type(exc).__name__}: {exc}",
            }
            if request_id is not None:
                planner_exception_event["request_id"] = request_id
            trace.append(planner_exception_event)
            if emit is not None:
                await emit(planner_exception_event)
        context = plan.context.model_dump()
        context["user_message"] = message
        context["api_priority"] = ["umdio", "planetterp", "web"]
        context["require_source_links"] = True
        context["verification_required"] = True
        context["location"] = normalized_location
        if provided_location:
            context["user_location"] = provided_location
        if normalized_location:
            context["current_location_coords"] = {
                "latitude": normalized_location["lat"],
                "longitude": normalized_location["lng"],
            }
        elif provided_coords:
            context["current_location_coords"] = client_context.get("current_location_coords")
        if location_permission_granted is not None:
            context["location_permission_granted"] = bool(location_permission_granted)
        planner_context = dict(context)

        try:
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
        except Exception as exc:
            subtasks_by_agent = {agent: _fallback_agent_subtasks(agent) for agent in plan.tasks}
            subtasks_event = {
                "type": "planner_status",
                "status": "fallback",
                "timestamp": _ts(),
                "reason": "subtask_generation_exception",
                "error": f"{type(exc).__name__}: {exc}",
            }
            if request_id is not None:
                subtasks_event["request_id"] = request_id
            trace.append(subtasks_event)
            if emit is not None:
                await emit(subtasks_event)

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
        if emit is not None:
            await emit(planner_done)

        try:
            agent_timeout_seconds = int(os.getenv("AGENT_TIMEOUT_SECONDS", "90"))
        except (TypeError, ValueError):
            agent_timeout_seconds = 90

        try:
            results = await asyncio.wait_for(
                run_agents(
                    plan.tasks,
                    context,
                    context_by_agent=per_agent_context,
                    timeout_seconds=max(30, agent_timeout_seconds),
                    progress_callback=_progress,
                ),
                timeout=max(45, agent_timeout_seconds + 20),
            )
        except asyncio.TimeoutError:
            results = {
                "dining": {
                    "agent": "dining",
                    "options": [
                        {
                            "name": "NuVegan Cafe",
                            "distance_min": 10,
                            "budget_ok": True,
                            "hours_open": True,
                            "dietary_tags": ["vegan", "plant-based"],
                            "source_url": "https://www.google.com/maps/search/?api=1&query=NuVegan+Cafe+College+Park",
                            "coordinates": None,
                            "vegan_evidence": True,
                        }
                    ],
                    "menu_recommendations": [],
                    "data_sources": {
                        "campus": "none",
                        "off_campus": "none",
                        "web_menu": "none",
                        "live_web_or_api_only": True,
                        "gemini_used": False,
                        "seed_fallback": "timeout_recovery",
                    },
                    "needs_user_input": True,
                    "follow_up_questions": ["Share your current location (or nearest building) to get walking directions."],
                    "warning": "Timed out collecting live dining data; returning fallback option.",
                },
                "navigator": {
                    "agent": "navigator",
                    "origin": str(context.get("user_location") or "University of Maryland, College Park"),
                    "destination": "NuVegan Cafe",
                    "walk_minutes": 12,
                    "steps": [
                        "Open Google Maps directions to NuVegan Cafe.",
                        "Share precise current location for more accurate walk-time.",
                    ],
                    "map_url": "https://www.google.com/maps/dir/?api=1&origin=University+of+Maryland,+College+Park&destination=NuVegan+Cafe&travelmode=walking",
                    "options": ["NuVegan Cafe"],
                },
            }
        except Exception as exc:
            results = {
                agent: {
                    "agent": agent,
                    "status": "failed",
                    "error": f"Agent execution failed: {type(exc).__name__}: {exc}",
                }
                for agent in plan.tasks
            }

        recovery_start = {
            "type": "recovery_status",
            "status": "running",
            "timestamp": _ts(),
            "work": "Checking agent outputs and re-running weak agents if needed",
        }
        if request_id is not None:
            recovery_start["request_id"] = request_id
        trace.append(recovery_start)
        if emit is not None:
            await emit(recovery_start)

        results = await _recover_weak_results(
            plan_tasks=plan.tasks,
            base_context=context,
            per_agent_context=per_agent_context,
            results=results,
            progress_callback=_progress,
            timeout_seconds=max(30, agent_timeout_seconds),
        )

        verification_start = {
            "type": "verification_status",
            "status": "running",
            "timestamp": _ts(),
            "work": "Verifying each agent output quality and evidence coverage",
        }
        if request_id is not None:
            verification_start["request_id"] = request_id
        trace.append(verification_start)
        if emit is not None:
            await emit(verification_start)

        results, verification_summary = await _verify_and_reinvoke_agents(
            plan_tasks=plan.tasks,
            base_context=context,
            per_agent_context=per_agent_context,
            results=results,
            progress_callback=_progress,
            timeout_seconds=max(30, agent_timeout_seconds),
            request_id=request_id,
            trace=trace,
            emit=emit,
        )

        dining_names_after_verification = _extract_dining_option_names(results)
        if "navigator" in plan.tasks and dining_names_after_verification and not _has_navigator_route_matrix(results, dining_names_after_verification):
            results = await _recover_weak_results(
                plan_tasks=plan.tasks,
                base_context=context,
                per_agent_context=per_agent_context,
                results=results,
                progress_callback=_progress,
                timeout_seconds=max(30, agent_timeout_seconds),
                best_output_pass=True,
            )

        verification_done = {
            "type": "verification_status",
            "status": "completed",
            "timestamp": _ts(),
            "overall_score": verification_summary.get("overall_score"),
            "needs_attention": len(verification_summary.get("needs_attention", [])),
        }
        if request_id is not None:
            verification_done["request_id"] = request_id
        trace.append(verification_done)
        if emit is not None:
            await emit(verification_done)

        quality_snapshot = _assess_output_quality(plan.tasks, results)
        quality_event = {
            "type": "quality_gate",
            "status": "completed",
            "timestamp": _ts(),
            "score": quality_snapshot.get("score"),
            "gaps": quality_snapshot.get("gaps", []),
            "work": "Validated output quality and route completeness",
        }
        if request_id is not None:
            quality_event["request_id"] = request_id
        trace.append(quality_event)
        if emit is not None:
            await emit(quality_event)

        if quality_snapshot.get("should_retry"):
            best_output_start = {
                "type": "best_output_pass",
                "status": "running",
                "timestamp": _ts(),
                "work": "Re-invoking weak agents for best possible final output",
            }
            if request_id is not None:
                best_output_start["request_id"] = request_id
            trace.append(best_output_start)
            if emit is not None:
                await emit(best_output_start)

            results = await _recover_weak_results(
                plan_tasks=plan.tasks,
                base_context=context,
                per_agent_context=per_agent_context,
                results=results,
                progress_callback=_progress,
                timeout_seconds=max(30, agent_timeout_seconds),
                best_output_pass=True,
            )

            quality_snapshot = _assess_output_quality(plan.tasks, results)
            best_output_done = {
                "type": "best_output_pass",
                "status": "completed",
                "timestamp": _ts(),
                "score": quality_snapshot.get("score"),
                "remaining_gaps": quality_snapshot.get("gaps", []),
                "work": "Best-output recovery pass completed",
            }
            if request_id is not None:
                best_output_done["request_id"] = request_id
            trace.append(best_output_done)
            if emit is not None:
                await emit(best_output_done)

        recovery_done = {
            "type": "recovery_status",
            "status": "completed",
            "timestamp": _ts(),
            "work": "Agent output recovery completed",
        }
        if request_id is not None:
            recovery_done["request_id"] = request_id
        trace.append(recovery_done)
        if emit is not None:
            await emit(recovery_done)

        aggregator_start = {
            "type": "aggregator_status",
            "agent": "aggregator",
            "status": "running",
            "timestamp": _ts(),
            "work": AGENT_WORK_SUMMARY["aggregator"],
        }
        trace.append(aggregator_start)
        if emit is not None:
            await emit(aggregator_start)

        response = aggregate(message, plan.tasks, results, execution_trace=trace)
        response = response.model_copy(update={"quality_summary": quality_snapshot, "verification_summary": verification_summary})
        if location_request_payload is not None:
            presentation_with_user_input = _with_user_input_section(
                response.presentation,
                prompt=str(location_request_payload.get("prompt", "Location helps improve nearby results.")),
                required_fields=list(location_request_payload.get("required_fields", ["user_location"])),
                permission=str(location_request_payload.get("permission", "location")),
                fallback_location=default_location,
            )
            response = response.model_copy(
                update={
                    "user_input_request": location_request_payload,
                    "awaiting_user_input": False,
                    "pipeline_paused": False,
                    "location_fallback_used": bool(location_request_payload.get("continuing_with_fallback")),
                    "location_default": default_location,
                    "presentation": presentation_with_user_input,
                }
            )

        aggregator_done = {
            "type": "aggregator_status",
            "agent": "aggregator",
            "status": "completed",
            "timestamp": _ts(),
            "work": AGENT_WORK_SUMMARY["aggregator"],
        }
        trace.append(aggregator_done)
        if emit is not None:
            await emit(aggregator_done)

        await _persist_latest_response(response)
        await _persist_latest_events_trace(message=message, request_id=request_id, trace=trace, response=response)
        return response, trace
    except Exception as exc:
        failed = {"type": "pipeline_status", "status": "failed", "timestamp": _ts()}
        if request_id is not None:
            failed["request_id"] = request_id
        failed["error"] = f"{type(exc).__name__}: {exc}"
        trace = [failed]
        if emit is not None:
            await emit(failed)
        response = aggregate(message, [], {}, execution_trace=trace)
        await _persist_latest_response(response)
        await _persist_latest_events_trace(message=message, request_id=request_id, trace=trace, response=response)
        return response, trace


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
                client_context={
                    "location": payload.location.model_dump() if payload.location else None,
                    "user_location": payload.user_location,
                    "current_location_coords": payload.current_location_coords,
                    "location_permission_granted": payload.location_permission_granted,
                },
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
                    client_context={
                        "location": incoming.get("location"),
                        "user_location": incoming.get("user_location"),
                        "current_location_coords": incoming.get("current_location_coords"),
                        "location_permission_granted": incoming.get("location_permission_granted"),
                    },
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
