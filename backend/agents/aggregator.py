from __future__ import annotations

from typing import Any

from backend.models.schemas import QueryResponse, QueryResults

RESULT_KEYS = [
    "schedule",
    "dining",
    "events",
    "finance",
    "navigator",
    "study_resources",
    "jobs_research",
]


def _normalize_events_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    events = payload.get("events")
    if isinstance(events, list):
        return {"agent": "events", "events": events}

    options = payload.get("options")
    if not isinstance(options, list):
        return None

    normalized_events: list[dict[str, Any]] = []
    for option in options:
        if not isinstance(option, dict):
            continue
        date_part = str(option.get("date", "")).strip()
        time_part = str(option.get("time", "")).strip()
        start = f"{date_part} {time_part}".strip()
        normalized_events.append(
            {
                "title": option.get("name", "Campus Event"),
                "location": option.get("location", "University of Maryland"),
                "start": start or "TBA",
                "free_food": bool(option.get("free_food", False)),
                "tags": list(option.get("tags", [])) if isinstance(option.get("tags"), list) else [],
            }
        )

    return {"agent": "events", "events": normalized_events}


def _normalize_results_for_schema(agent_results: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {key: None for key in RESULT_KEYS}

    schedule = agent_results.get("schedule")
    if isinstance(schedule, dict) and isinstance(schedule.get("study_blocks"), list) and isinstance(schedule.get("next_deadline"), dict):
        normalized["schedule"] = {
            "agent": "schedule",
            "study_blocks": schedule.get("study_blocks", []),
            "next_deadline": schedule.get("next_deadline", {}),
            **{k: v for k, v in schedule.items() if k not in {"agent", "study_blocks", "next_deadline"}},
        }

    dining = agent_results.get("dining")
    if isinstance(dining, dict) and isinstance(dining.get("options"), list):
        normalized["dining"] = dining

    events = agent_results.get("events")
    if isinstance(events, dict):
        normalized["events"] = _normalize_events_payload(events)

    finance = agent_results.get("finance")
    if isinstance(finance, dict) and all(field in finance for field in ["weekly_spent", "budget_remaining", "suggestion"]):
        normalized["finance"] = {"agent": "finance", **finance}

    navigator = agent_results.get("navigator")
    if isinstance(navigator, dict) and all(field in navigator for field in ["origin", "destination", "walk_minutes", "steps", "map_url"]):
        normalized["navigator"] = {"agent": "navigator", **navigator}

    study_resources = agent_results.get("study_resources")
    if isinstance(study_resources, dict) and isinstance(study_resources.get("tutoring"), list) and isinstance(study_resources.get("office_hours"), list):
        normalized["study_resources"] = {"agent": "study_resources", **study_resources}

    jobs_research = agent_results.get("jobs_research")
    if isinstance(jobs_research, dict) and all(field in jobs_research for field in ["jobs", "labs", "cold_email"]):
        normalized["jobs_research"] = {"agent": "jobs_research", **jobs_research}

    return normalized


def _build_visual_presentation(query: str, agents_used: list[str], agent_results: dict[str, Any]) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    quick_actions: list[dict[str, Any]] = []
    highlights: list[str] = []

    activation_items: list[dict[str, Any]] = []
    error_count = 0
    for agent_name in agents_used:
        payload = agent_results.get(agent_name)
        if not isinstance(payload, dict):
            activation_items.append(
                {
                    "agent": agent_name,
                    "status": "no_output",
                    "gemini_used": None,
                    "error": "No payload returned",
                }
            )
            error_count += 1
            continue

        error = payload.get("error")
        data_sources = payload.get("data_sources") if isinstance(payload.get("data_sources"), dict) else {}
        activation_items.append(
            {
                "agent": agent_name,
                "status": "error" if error else "ok",
                "gemini_used": data_sources.get("gemini_used"),
                "error": error,
            }
        )
        if error:
            error_count += 1

    sections.append(
        {
            "id": "agent_activation",
            "title": "Activated Agents",
            "agent": "system",
            "style": "status",
            "items": activation_items,
        }
    )
    highlights.append(f"Activated agents: {', '.join(agents_used) if agents_used else 'none'}")
    if error_count:
        highlights.append(f"Agents with errors: {error_count}")

    dining = agent_results.get("dining") if isinstance(agent_results.get("dining"), dict) else {}
    dining_options = dining.get("options", []) if isinstance(dining.get("options"), list) else []
    if dining_options:
        sections.append(
            {
                "id": "dining",
                "title": "Dining Options",
                "agent": "dining",
                "style": "cards",
                "items": dining_options[:6],
                "meta": {
                    "menu_recommendations": dining.get("menu_recommendations", []),
                    "route_preview": dining.get("route_preview"),
                },
            }
        )
        highlights.append(f"Found {len(dining_options)} dining options")
        quick_actions.append({"label": "Open Dining Route", "agent": "dining", "action": "open_map", "target": dining.get("route_preview", {}).get("map_url")})

    navigator = agent_results.get("navigator") if isinstance(agent_results.get("navigator"), dict) else {}
    if navigator:
        sections.append(
            {
                "id": "navigation",
                "title": "Navigation",
                "agent": "navigator",
                "style": "route",
                "items": [
                    {
                        "origin": navigator.get("origin"),
                        "destination": navigator.get("destination"),
                        "walk_minutes": navigator.get("walk_minutes"),
                        "steps": navigator.get("steps", []),
                        "map_url": navigator.get("map_url"),
                    }
                ],
            }
        )
        highlights.append("Route and walking directions prepared")
        quick_actions.append({"label": "Open Campus Map", "agent": "navigator", "action": "open_map", "target": navigator.get("map_url")})

    events = agent_results.get("events") if isinstance(agent_results.get("events"), dict) else {}
    events_items = events.get("event_recommendations") or events.get("options") or events.get("events")
    if isinstance(events_items, list) and events_items:
        sections.append(
            {
                "id": "events",
                "title": "Events",
                "agent": "events",
                "style": "timeline",
                "items": events_items[:6],
            }
        )
        highlights.append(f"Found {len(events_items)} events")

    schedule = agent_results.get("schedule") if isinstance(agent_results.get("schedule"), dict) else {}
    if schedule:
        sections.append(
            {
                "id": "schedule",
                "title": "Schedule",
                "agent": "schedule",
                "style": "timeline",
                "items": schedule.get("study_blocks", []),
                "meta": {"next_deadline": schedule.get("next_deadline")},
            }
        )

    finance = agent_results.get("finance") if isinstance(agent_results.get("finance"), dict) else {}
    if finance:
        sections.append(
            {
                "id": "finance",
                "title": "Budget",
                "agent": "finance",
                "style": "stats",
                "items": [
                    {
                        "weekly_spent": finance.get("weekly_spent"),
                        "budget_remaining": finance.get("budget_remaining"),
                        "suggestion": finance.get("suggestion"),
                    }
                ],
            }
        )

    study_resources = agent_results.get("study_resources") if isinstance(agent_results.get("study_resources"), dict) else {}
    if study_resources:
        sections.append(
            {
                "id": "study_resources",
                "title": "Study Resources",
                "agent": "study_resources",
                "style": "list",
                "items": study_resources.get("tutoring", []) + study_resources.get("office_hours", []),
            }
        )

    jobs = agent_results.get("jobs_research") if isinstance(agent_results.get("jobs_research"), dict) else {}
    if jobs:
        sections.append(
            {
                "id": "jobs_research",
                "title": "Jobs and Research",
                "agent": "jobs_research",
                "style": "cards",
                "items": jobs.get("jobs", []) + jobs.get("labs", []),
                "meta": {"cold_email": jobs.get("cold_email")},
            }
        )

    if not highlights:
        highlights.append("No agent results available yet")

    successful_agents = sum(1 for item in activation_items if item.get("status") == "ok")
    errored_agents = sum(1 for item in activation_items if item.get("status") == "error")
    missing_agents = sum(1 for item in activation_items if item.get("status") == "no_output")

    visual_report = {
        "headline": f"{len(agents_used)} agent{'s' if len(agents_used) != 1 else ''} synthesized into one campus report",
        "subheadline": "Structured text, numbers, and live agent results are normalized for visual rendering.",
        "metrics": [
            {
                "label": "Activated agents",
                "value": len(agents_used),
                "suffix": "agents",
                "tone": "accent",
            },
            {
                "label": "Healthy outputs",
                "value": successful_agents,
                "suffix": f"/ {len(agents_used)}",
                "tone": "success",
            },
            {
                "label": "Highlights",
                "value": len(highlights),
                "suffix": "notes",
                "tone": "warning",
            },
            {
                "label": "Quick actions",
                "value": len(quick_actions),
                "suffix": "links",
                "tone": "neutral",
            },
        ],
        "charts": [
            {
                "id": "agent_coverage",
                "title": "Agent Coverage",
                "kind": "bar",
                "data": [
                    {
                        "label": item.get("agent"),
                        "value": 100 if item.get("status") == "ok" else 45 if item.get("status") == "error" else 12,
                        "detail": item.get("status"),
                    }
                    for item in activation_items
                ],
            },
            {
                "id": "output_health",
                "title": "Output Health",
                "kind": "pie",
                "data": [
                    {"label": "Ready", "value": successful_agents},
                    {"label": "Errored", "value": errored_agents},
                    {"label": "Missing", "value": missing_agents},
                ],
                "colors": ["#16A34A", "#DC2626", "#9CA3AF"],
            },
        ],
        "story_points": highlights[:5],
        "section_count": len(sections),
    }

    return {
        "layout": "dashboard",
        "summary": {
            "title": "TerpAI Results",
            "query": query,
            "active_agents": agents_used,
            "highlights": highlights,
        },
        "sections": sections,
        "quick_actions": [action for action in quick_actions if action.get("target")],
        "visual_report": visual_report,
    }


def aggregate(
    query: str,
    agents_used: list[str],
    agent_results: dict,
    execution_trace: list[dict[str, Any]] | None = None,
) -> QueryResponse:
    payload = _normalize_results_for_schema(agent_results)
    presentation = _build_visual_presentation(query, agents_used, agent_results)
    agent_execution = {
        "active_agents": agents_used,
        "timeline": execution_trace or [],
    }

    return QueryResponse(
        query=query,
        agents_used=agents_used,
        results=QueryResults(**payload),
        presentation=presentation,
        agent_execution=agent_execution,
        agent_outputs={k: v for k, v in agent_results.items() if k in RESULT_KEYS},
    )
