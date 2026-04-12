from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

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


def _collect_links(value: Any) -> list[str]:
    links: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                lowered = str(key).lower()
                if lowered.endswith("url") and isinstance(item, str) and item.startswith(("http://", "https://")):
                    links.append(item)
                else:
                    _walk(item)
            return
        if isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(value)
    deduped: list[str] = []
    seen: set[str] = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        deduped.append(link)
    return deduped[:30]


def _agent_numeric_snapshot(agent: str, payload: dict[str, Any]) -> dict[str, Any]:
    if agent == "dining":
        options = payload.get("options") if isinstance(payload.get("options"), list) else []
        return {"options": len(options)}
    if agent == "events":
        events = payload.get("events") if isinstance(payload.get("events"), list) else payload.get("options") if isinstance(payload.get("options"), list) else []
        return {"events": len(events)}
    if agent == "schedule":
        blocks = payload.get("study_blocks") if isinstance(payload.get("study_blocks"), list) else []
        return {"study_blocks": len(blocks)}
    if agent == "study_resources":
        tutoring = payload.get("tutoring") if isinstance(payload.get("tutoring"), list) else []
        office_hours = payload.get("office_hours") if isinstance(payload.get("office_hours"), list) else []
        resources = payload.get("resources") if isinstance(payload.get("resources"), list) else []
        return {"tutoring": len(tutoring), "office_hours": len(office_hours), "resources": len(resources)}
    if agent == "navigator":
        steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
        return {"steps": len(steps), "walk_minutes": payload.get("walk_minutes")}
    if agent == "jobs_research":
        jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
        labs = payload.get("labs") if isinstance(payload.get("labs"), list) else []
        return {"jobs": len(jobs), "labs": len(labs)}
    if agent == "finance":
        return {"weekly_spent": payload.get("weekly_spent"), "budget_remaining": payload.get("budget_remaining")}
    return {}


def _normalize_jobs_research_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
    labs = payload.get("labs") if isinstance(payload.get("labs"), list) else []

    normalized_jobs: list[dict[str, Any]] = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("position") or item.get("name") or "").strip()
        apply_url = str(item.get("apply_url") or item.get("link") or item.get("url") or "").strip()
        if not title or not apply_url:
            continue
        normalized_jobs.append(
            {
                "title": title,
                "department": str(item.get("department") or item.get("source") or "UMD").strip() or "UMD",
                "pay": str(item.get("pay") or item.get("salary") or "N/A").strip() or "N/A",
                "apply_url": apply_url,
            }
        )

    normalized_labs: list[dict[str, Any]] = []
    for item in labs:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic") or item.get("opportunity") or item.get("title") or "").strip()
        contact = str(item.get("contact") or item.get("link") or item.get("url") or "").strip()
        if not topic or not contact:
            continue
        normalized_labs.append(
            {
                "pi": str(item.get("pi") or "TBD").strip() or "TBD",
                "department": str(item.get("department") or item.get("source") or "UMD").strip() or "UMD",
                "topic": topic,
                "contact": contact,
            }
        )

    cold_email = str(payload.get("cold_email") or payload.get("research_email_template") or "").strip()
    if not normalized_jobs and not normalized_labs and not cold_email:
        return None

    return {
        "agent": "jobs_research",
        "jobs": normalized_jobs,
        "labs": normalized_labs,
        "cold_email": cold_email,
    }


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
    if isinstance(jobs_research, dict):
        normalized_jobs_research = _normalize_jobs_research_payload(jobs_research)
        if normalized_jobs_research is not None:
            normalized["jobs_research"] = normalized_jobs_research

    return normalized


def _build_combined_output(agent_results: dict[str, Any]) -> dict[str, Any] | None:
    dining = agent_results.get("dining") if isinstance(agent_results.get("dining"), dict) else {}
    navigator = agent_results.get("navigator") if isinstance(agent_results.get("navigator"), dict) else {}

    options = dining.get("options") if isinstance(dining.get("options"), list) else []
    if not options:
        return None

    navigator_origin = str(navigator.get("origin") or "current location")
    combined_items: list[dict[str, Any]] = []

    for option in options[:8]:
        if not isinstance(option, dict):
            continue
        name = str(option.get("name") or "").strip()
        if not name:
            continue
        coords = option.get("coordinates") if isinstance(option.get("coordinates"), list) else None
        map_url: str
        if coords and len(coords) == 2:
            destination = f"{coords[0]},{coords[1]}"
            map_url = (
                "https://www.google.com/maps/dir/?api=1"
                f"&origin={quote_plus(navigator_origin)}"
                f"&destination={quote_plus(destination)}"
                "&travelmode=walking"
            )
        else:
            map_url = (
                "https://www.google.com/maps/dir/?api=1"
                f"&origin={quote_plus(navigator_origin)}"
                f"&destination={quote_plus(name)}"
                "&travelmode=walking"
            )

        combined_items.append(
            {
                "name": name,
                "distance_min": option.get("distance_min"),
                "dietary_tags": option.get("dietary_tags", []),
                "vegan_evidence": bool(option.get("vegan_evidence")),
                "coordinates": coords,
                "source_url": option.get("source_url"),
                "route_map_url": map_url,
            }
        )

    if not combined_items:
        return None

    return {
        "origin": navigator_origin,
        "restaurants": combined_items,
        "data_sources": {
            "dining": dining.get("data_sources"),
            "navigator": {"map_url": navigator.get("map_url")},
        },
    }


def _build_visual_presentation(query: str, agents_used: list[str], agent_results: dict[str, Any]) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    quick_actions: list[dict[str, Any]] = []
    highlights: list[str] = []
    source_link_items: list[dict[str, Any]] = []
    agent_detail_items: list[dict[str, Any]] = []

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
        partial = False
        if agent_name == "dining":
            options = payload.get("options") if isinstance(payload.get("options"), list) else []
            if not options and not error:
                partial = True
        data_sources = payload.get("data_sources") if isinstance(payload.get("data_sources"), dict) else {}
        activation_items.append(
            {
                "agent": agent_name,
                "status": "error" if error else ("partial" if partial else "ok"),
                "gemini_used": data_sources.get("gemini_used"),
                "error": error,
            }
        )
        if error:
            error_count += 1

        numeric = _agent_numeric_snapshot(agent_name, payload)
        text_summary = ""
        for text_key in ["ai_recommendation", "ai_summary", "suggestion", "warning", "completion_message"]:
            text_value = payload.get(text_key)
            if isinstance(text_value, str) and text_value.strip():
                text_summary = text_value.strip()
                break
        links = _collect_links(payload)
        for link in links[:8]:
            source_link_items.append({"agent": agent_name, "url": link})
        agent_detail_items.append(
            {
                "agent": agent_name,
                "numeric": numeric,
                "text_summary": text_summary,
                "source_link_count": len(links),
            }
        )

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
    if dining:
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
                    "warning": dining.get("warning"),
                    "follow_up_questions": dining.get("follow_up_questions", []),
                },
            }
        )
        if dining_options:
            highlights.append(f"Found {len(dining_options)} dining options")
        elif dining.get("warning"):
            highlights.append(str(dining.get("warning")))
        quick_actions.append({"label": "Open Dining Route", "agent": "dining", "action": "open_map", "target": dining.get("route_preview", {}).get("map_url")})

    navigator = agent_results.get("navigator") if isinstance(agent_results.get("navigator"), dict) else {}
    if navigator:
        navigator_options = navigator.get("options", []) if isinstance(navigator.get("options"), list) else []
        navigator_routes = navigator.get("routes_by_option", []) if isinstance(navigator.get("routes_by_option"), list) else []
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
                        "options": navigator_options,
                        "routes_by_option": navigator_routes,
                    }
                ],
            }
        )
        highlights.append("Route and walking directions prepared")
        quick_actions.append({"label": "Open Campus Map", "agent": "navigator", "action": "open_map", "target": navigator.get("map_url")})
        for route in navigator_routes[:5]:
            if not isinstance(route, dict):
                continue
            destination_name = str(route.get("destination") or route.get("name") or "").strip()
            map_url = route.get("map_url")
            if destination_name and map_url:
                quick_actions.append({"label": f"Route to {destination_name}", "agent": "navigator", "action": "open_map", "target": map_url})
        if navigator_options:
            destination = str(navigator.get("origin") or "current location")
            for name in navigator_options[:3]:
                quick_actions.append(
                    {
                        "label": f"Route to {name}",
                        "agent": "navigator",
                        "action": "open_map",
                        "target": (
                            "https://www.google.com/maps/dir/?api=1"
                            f"&origin={quote_plus(destination)}"
                            f"&destination={quote_plus(str(name))}"
                            "&travelmode=walking"
                        ),
                    }
                )

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

    if agent_detail_items:
        sections.append(
            {
                "id": "agent_details",
                "title": "Agent Details",
                "agent": "system",
                "style": "table",
                "items": agent_detail_items,
            }
        )

    if source_link_items:
        sections.append(
            {
                "id": "sources",
                "title": "Sources",
                "agent": "system",
                "style": "links",
                "items": source_link_items[:24],
            }
        )
        highlights.append(f"Collected {len(source_link_items)} source links")
        for item in source_link_items[:3]:
            quick_actions.append(
                {
                    "label": f"Open source ({item.get('agent')})",
                    "agent": str(item.get("agent") or "system"),
                    "action": "open_url",
                    "target": item.get("url"),
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
    combined_output = _build_combined_output(agent_results)
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
        combined_output=combined_output,
    )
