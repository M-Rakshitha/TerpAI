from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, TypedDict
from urllib.parse import quote_plus

import requests
from backend.utils.runtime_flags import strict_live_mode_enabled
from backend.utils.ai_workflow import call_gemini_with_retry
from backend.utils.gemini_client import GeminiClientError

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:
    LANGGRAPH_AVAILABLE = False
    END = None
    StateGraph = None

# External websites
UMD_CALENDAR_HOME = "https://calendar.umd.edu/"
UMD_CALENDAR_GRAPHQL = "https://calendar.umd.edu/graphql"
EVENTBRITE_SEARCH_URL = "https://www.eventbrite.com/d/md--college-park/events/"
UMD_EVENTS_RSS = "https://news.umd.edu/events/upcoming"

EVENT_KEYWORDS = [
    "concert",
    "seminar",
    "lecture",
    "workshop",
    "conference",
    "networking",
    "social",
    "sports",
    "career fair",
    "club fair",
    "performance",
    "festival",
    "movie",
    "comedy",
    "trivia",
    "dance",
    "party",
]

DIETARY_KEYWORDS = {
    "vegan": ["vegan", "plant-based"],
    "vegetarian": ["vegetarian", "veg"],
    "halal": ["halal"],
    "gluten-free": ["gluten free", "gluten-free", "gf"],
    "kosher": ["kosher"],
}

TIME_KEYWORDS = {
    "today": 0,
    "tomorrow": 1,
    "next week": 7,
    "this weekend": 2,
    "evening": "evening",
    "morning": "morning",
    "afternoon": "afternoon",
    "night": "night",
}

KNOWN_UMD_EVENTS = {
    "McKeldin Library Cleanup": {
        "time": "11:00 AM",
        "date_offset_days": 0,
        "location": "McKeldin Library, University of Maryland",
        "tags": ["club", "community service"],
        "free_food": False,
        "category": "community",
    },
    "Engineering Career Fair": {
        "time": "2:00 PM",
        "date_offset_days": 3,
        "location": "Stamp Student Union, University of Maryland",
        "tags": ["career", "engineering", "networking"],
        "free_food": True,
        "category": "career",
    },
    "Student Organization Fair": {
        "time": "12:00 PM",
        "date_offset_days": 7,
        "location": "Stamp Student Union, University of Maryland",
        "tags": ["student", "club"],
        "free_food": True,
        "category": "community",
    },
    "Campus Movie Night": {
        "time": "8:00 PM",
        "date_offset_days": 2,
        "location": "Nyumburu Cultural Center, University of Maryland",
        "tags": ["entertainment", "social"],
        "free_food": True,
        "category": "social",
    },
    "Mathematics Colloquium": {
        "time": "3:30 PM",
        "date_offset_days": 4,
        "location": "Mathematics Library, University of Maryland",
        "tags": ["academic", "lecture", "mathematics"],
        "free_food": False,
        "category": "academic",
    },
}


class EventsState(TypedDict, total=False):
    context: dict[str, Any]
    user_message: str
    interested_categories: list[str]
    dietary_preferences: list[str]
    date_preference: str | None
    time_preference: str | None
    free_food_only: bool
    campus_events: list[dict[str, Any]]
    nearby_events: list[dict[str, Any]]
    campus_failures: int
    nearby_failures: int
    ranked_events: list[dict[str, Any]]
    registration_links: dict[str, str]
    needs_user_input: bool
    follow_up_questions: list[str]
    result: dict[str, Any]


def _extract_categories_from_message(message: str) -> list[str]:
    lowered = message.lower()
    found: list[str] = []
    for keyword in EVENT_KEYWORDS:
        if keyword in lowered:
            found.append(keyword)
    return list(dict.fromkeys(found)) if found else ["general"]


def _extract_dietary_from_message(message: str) -> list[str]:
    lowered = message.lower()
    found: list[str] = []
    for label, needles in DIETARY_KEYWORDS.items():
        if any(needle in lowered for needle in needles):
            found.append(label)
    return found


def _extract_date_preference(message: str) -> str | None:
    lowered = message.lower()
    for date_term in TIME_KEYWORDS.keys():
        if date_term in lowered:
            return date_term
    return None


def _extract_time_preference(message: str) -> str | None:
    lowered = message.lower()
    for time_term in ["evening", "morning", "afternoon", "night"]:
        if time_term in lowered:
            return time_term
    return None


def _check_free_food_mention(message: str) -> bool:
    lowered = message.lower()
    return any(phrase in lowered for phrase in ["free food", "food", "snacks", "refreshments"])


def _fetch_html(url: str) -> str:
    response = requests.get(url, timeout=6, headers={"User-Agent": "terpai-backend/0.1"})
    response.raise_for_status()
    return response.text


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _extract_public_token(html: str) -> str | None:
    match = re.search(r"data-token=([^>\s]+)", html)
    if match:
        return match.group(1).strip('"\'')
    return None


def _extract_title_tags(text: str) -> list[str]:
    lowered = text.lower()
    found = [keyword for keyword in EVENT_KEYWORDS if keyword in lowered]
    return found or ["general"]


def _date_from_month_day(month_value: str | None, day_value: str | None) -> str | None:
    if not month_value or not day_value:
        return None

    month_text = str(month_value).strip()
    day_text = str(day_value).strip()
    for date_format in ("%b %d %Y", "%B %d %Y"):
        try:
            date_value = datetime.strptime(f"{month_text} {day_text} {datetime.now().year}", date_format)
            return date_value.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _date_from_label(label: str) -> str | None:
    normalized = label.strip()
    lowered = normalized.lower()
    today = datetime.now()

    if lowered == "today":
        return today.strftime("%Y-%m-%d")
    if lowered == "tomorrow":
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    weekday_map = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for weekday_name, weekday_number in weekday_map.items():
        if lowered.startswith(weekday_name):
            days_ahead = (weekday_number - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    source = normalized if re.search(r"\b\d{4}\b", normalized) else f"{normalized} {today.year}"
    for date_format in ("%a, %b %d %Y", "%A, %b %d %Y", "%b %d %Y"):
        try:
            parsed = datetime.strptime(source, date_format)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _extract_date_and_time(text: str, title: str) -> tuple[str | None, str | None]:
    title_index = text.find(title)
    if title_index == -1:
        return None, None

    window = text[title_index : title_index + 240]
    match = re.search(
        r"(?P<label>(?:Today|Tomorrow|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+[A-Z][a-z]{2}\s+\d{1,2}|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*))\s*[•\-|]\s*(?P<time>[^\n•|]+)",
        window,
    )
    if match:
        return _date_from_label(match.group("label")), match.group("time").strip()

    return None, None


def _fetch_live_campus_events() -> list[dict[str, Any]]:
    try:
        home_html = _fetch_html(UMD_CALENDAR_HOME)
        token = _extract_public_token(home_html)
        if token:
            query = (
                "query getEvents($startDate: String!, $related: [QueryArgument]) {"
                " entries: solspace_calendar {"
                " events(relatedTo: $related loadOccurrences: true startsAfterOrAt: $startDate limit: 12 calendarId: [4, 2]) {"
                " title url startMonth: startDate @formatDateTime(format: \"M\")"
                " startDay: startDate @formatDateTime(format: \"d\")"
                " endMonth: endDate @formatDateTime(format: \"M\")"
                " endDay: endDate @formatDateTime(format: \"d\")"
                " } } }"
            )
            response = requests.post(
                UMD_CALENDAR_GRAPHQL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "terpai-backend/0.1",
                },
                json={"query": query, "variables": {"startDate": datetime.now().strftime("%Y-%m-%d"), "related": []}},
                timeout=8,
            )
            response.raise_for_status()
            payload = response.json()
            entries = payload.get("data", {}).get("entries", {}) if isinstance(payload, dict) else {}
            events_payload = entries.get("events", []) if isinstance(entries, dict) else []
            if isinstance(events_payload, list):
                events: list[dict[str, Any]] = []
                for item in events_payload:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title", "")).strip()
                    if not title:
                        continue

                    date_value = _date_from_month_day(item.get("startMonth"), item.get("startDay")) or datetime.now().strftime("%Y-%m-%d")
                    url = str(item.get("url", "")).strip()
                    event_text = title.lower()
                    events.append(
                        {
                            "name": title,
                            "date": date_value,
                            "time": "TBA",
                            "location": "University of Maryland",
                            "url": url,
                            "tags": _extract_title_tags(event_text),
                            "free_food": any(term in event_text for term in ["food", "snack", "refreshment"]),
                            "category": "campus",
                        }
                    )
                if events:
                    return events
    except Exception:
        pass

    return []


def _query_eventbrite_nearby() -> list[dict[str, Any]]:
    try:
        html = _fetch_html(EVENTBRITE_SEARCH_URL)
        text = _strip_html(html)
        events: list[dict[str, Any]] = []
        seen: set[str] = set()

        for match in re.finditer(r'aria-label="View ([^"]+)"', html):
            title = match.group(1).strip()
            if not title or title in seen:
                continue

            seen.add(title)
            chunk = html[max(0, match.start() - 700) : match.start() + 1600]
            url_match = re.search(r'href="([^"]+)"', chunk)
            location_match = re.search(r'data-event-location="([^"]*)"', chunk)
            paid_match = re.search(r'data-event-paid-status="([^"]*)"', chunk)

            date_value, time_value = _extract_date_and_time(text, title)
            if not date_value:
                date_value = datetime.now().strftime("%Y-%m-%d")

            events.append(
                {
                    "name": title,
                    "date": date_value,
                    "time": time_value or "TBA",
                    "location": location_match.group(1).strip() if location_match else "College Park, MD",
                    "url": url_match.group(1).strip() if url_match else "",
                    "tags": ["eventbrite", "nearby"],
                    "free_food": (paid_match.group(1).lower() == "free") if paid_match else False,
                    "category": "nearby",
                }
            )

            if len(events) >= 10:
                break
        return events
    except Exception:
        return []


def _node_ingest_context(state: EventsState) -> EventsState:
    context = state.get("context", {})
    message = str(context.get("user_message", ""))

    categories = _extract_categories_from_message(message)
    dietary = _extract_dietary_from_message(message)
    date_pref = _extract_date_preference(message)
    time_pref = _extract_time_preference(message)
    free_food_only = _check_free_food_mention(message)

    return {
        "user_message": message,
        "interested_categories": categories,
        "dietary_preferences": dietary,
        "date_preference": date_pref,
        "time_preference": time_pref,
        "free_food_only": free_food_only,
    }


def _node_fetch_campus_events(state: EventsState) -> EventsState:
    try:
        events = _fetch_live_campus_events()
        failures = 0 if events else 1
    except Exception:
        events = []
        failures = 1

    return {"campus_events": events, "campus_failures": failures}


def _node_fetch_nearby_events(state: EventsState) -> EventsState:
    try:
        nearby = _query_eventbrite_nearby()
        failures = 0 if nearby else 1
    except Exception:
        nearby = []
        failures = 1

    return {"nearby_events": nearby, "nearby_failures": failures}


def _node_rank_events(state: EventsState) -> EventsState:
    categories = state.get("interested_categories", ["general"])
    dietary = state.get("dietary_preferences", [])
    date_pref = state.get("date_preference") or "today"
    time_pref = state.get("time_preference")
    free_food_only = state.get("free_food_only", False)

    combined = state.get("campus_events", []) + state.get("nearby_events", [])

    def _score(event: dict[str, Any]) -> float:
        score = 0.0

        # Category match
        event_tags = [tag.lower() for tag in event.get("tags", [])]
        for cat in categories:
            if cat.lower() in event_tags or cat.lower() in event.get("category", "").lower():
                score += 3.0

        # Date preference
        date_str = event.get("date", "")
        if date_pref == "today" and date_str == datetime.now().strftime("%Y-%m-%d"):
            score += 2.0
        elif date_pref == "tomorrow" and date_str == (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"):
            score += 2.0
        elif date_pref == "this weekend":
            event_date = datetime.strptime(date_str, "%Y-%m-%d")
            if event_date.weekday() in (5, 6):
                score += 2.0

        # Time preference
        if time_pref:
            time_str = event.get("time", "").lower()
            if time_pref == "morning" and any(x in time_str for x in ["7", "8", "9", "10"]):
                score += 1.5
            elif time_pref == "afternoon" and any(x in time_str for x in ["12", "1", "2", "3", "4"]):
                score += 1.5
            elif time_pref == "evening" and any(x in time_str for x in ["5", "6", "7", "8", "9"]):
                score += 1.5
            elif time_pref == "night" and any(x in time_str for x in ["8", "9", "10", "11"]):
                score += 1.5

        # Free food bonus
        if event.get("free_food"):
            score += 1.0

        # Penalty if free_food_only is set and event has no food
        if free_food_only and not event.get("free_food"):
            score -= 5.0

        # Campus events get slight boost
        if event.get("category") == "campus":
            score += 0.5

        return score

    ranked = sorted(combined, key=_score, reverse=True)
    return {"ranked_events": ranked[:10]}


def _node_build_registration_links(state: EventsState) -> EventsState:
    ranked = state.get("ranked_events", [])
    links: dict[str, str] = {}

    for event in ranked[:5]:
        name = event.get("name", "")
        url = event.get("url", "")

        # If no URL, generate Google search
        if not url:
            url = f"https://www.google.com/search?q={quote_plus(f'{name} UMD College Park')}"

        links[name] = url

    return {"registration_links": links}


def _node_build_result(state: EventsState) -> EventsState:
    ranked = state.get("ranked_events", [])

    options = [
        {
            "name": event.get("name"),
            "date": event.get("date"),
            "time": event.get("time"),
            "location": event.get("location"),
            "tags": event.get("tags", []),
            "free_food": bool(event.get("free_food", False)),
        }
        for event in ranked
    ]

    recommendations = [
        {
            "name": event.get("name"),
            "date": event.get("date"),
            "time": event.get("time"),
            "location": event.get("location"),
            "category": event.get("category"),
            "free_food": event.get("free_food"),
            "registration_url": state.get("registration_links", {}).get(event.get("name", ""), ""),
        }
        for event in ranked[:5]
    ]

    needs_input = False
    follow_up: list[str] = []

    if not state.get("interested_categories") or state.get("interested_categories") == ["general"]:
        needs_input = True
        follow_up.append("What type of events are you interested in? (concert, career fair, social, etc.)")

    if not state.get("date_preference"):
        needs_input = True
        follow_up.append("When do you want to attend? (today, tomorrow, this weekend, next week, etc.)")

    result: dict[str, Any] = {
        "agent": "events",
        "options": options,
        "event_recommendations": recommendations,
        "recommendation_basis": {
            "interested_categories": state.get("interested_categories", []),
            "dietary_preferences": state.get("dietary_preferences", []),
            "date_preference": state.get("date_preference"),
            "time_preference": state.get("time_preference"),
            "free_food_only": state.get("free_food_only", False),
        },
    }

    if needs_input:
        result["needs_user_input"] = True
        result["follow_up_questions"] = follow_up

    return {"result": result}


def _build_graph() -> Any | None:
    if not LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(EventsState)
    graph.add_node("ingest_context", _node_ingest_context)
    graph.add_node("fetch_campus_events", _node_fetch_campus_events)
    graph.add_node("fetch_nearby_events", _node_fetch_nearby_events)
    graph.add_node("rank_events", _node_rank_events)
    graph.add_node("build_registration_links", _node_build_registration_links)
    graph.add_node("build_result", _node_build_result)
    graph.set_entry_point("ingest_context")
    graph.add_edge("ingest_context", "fetch_campus_events")
    graph.add_edge("fetch_campus_events", "fetch_nearby_events")
    graph.add_edge("fetch_nearby_events", "rank_events")
    graph.add_edge("rank_events", "build_registration_links")
    graph.add_edge("build_registration_links", "build_result")
    graph.add_edge("build_result", END)
    return graph.compile()


EVENTS_GRAPH = _build_graph()


def _run_without_langgraph(initial_state: EventsState) -> EventsState:
    state: EventsState = dict(initial_state)
    state.update(_node_ingest_context(state))
    state.update(_node_fetch_campus_events(state))
    state.update(_node_fetch_nearby_events(state))
    state.update(_node_rank_events(state))
    state.update(_node_build_registration_links(state))
    state.update(_node_build_result(state))
    return state


async def _generate_ai_event_summary(user_message: str, result: dict[str, Any]) -> str:
    options = result.get("options", []) if isinstance(result.get("options"), list) else []
    top = options[:4]
    prompt = (
        "You are a UMD events assistant. "
        "Given the user request and candidate events, write a concise 2-3 sentence recommendation with one best pick and one backup.\n\n"
        f"User query: {user_message}\n"
        f"Candidate events: {top}\n"
    )
    return await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 4)


async def _generate_gemini_event_options(
    user_message: str,
    categories: list[str],
    date_preference: str | None,
) -> list[dict[str, Any]]:
    prompt = (
        "You are a UMD events assistant using web knowledge. "
        "Return ONLY valid JSON as an array of 3 to 5 event objects with keys: "
        "name, date (YYYY-MM-DD), time, location, tags (array), free_food (boolean), category.\n\n"
        f"User query: {user_message}\n"
        f"Categories: {categories}\n"
        f"Date preference: {date_preference or 'not specified'}\n"
    )
    raw = await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 10)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        payload = json.loads(cleaned)
    except Exception:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            payload = json.loads(cleaned[start : end + 1])
        except Exception:
            return []

    if not isinstance(payload, list):
        return []

    options: list[dict[str, Any]] = []
    for item in payload[:5]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        options.append(
            {
                "name": name,
                "date": str(item.get("date", datetime.now().strftime("%Y-%m-%d"))),
                "time": str(item.get("time", "TBA")),
                "location": str(item.get("location", "University of Maryland")),
                "tags": [str(tag) for tag in item.get("tags", []) if str(tag).strip()],
                "free_food": bool(item.get("free_food", False)),
                "category": str(item.get("category", "campus")),
            }
        )
    return options


async def run(context: dict) -> dict:
    effective_context = dict(context)
    if isinstance(effective_context.get("agent_prompt"), str) and effective_context.get("agent_prompt"):
        effective_context["user_message"] = effective_context["agent_prompt"]

    initial_state: EventsState = {"context": effective_context}

    try:
        if EVENTS_GRAPH is not None:
            final_state = await asyncio.wait_for(asyncio.to_thread(EVENTS_GRAPH.invoke, initial_state), timeout=8)
        else:
            final_state = await asyncio.wait_for(asyncio.to_thread(_run_without_langgraph, initial_state), timeout=8)

        result = final_state.get("result") if isinstance(final_state, dict) else None
        if isinstance(result, dict) and result.get("agent") == "events" and result.get("options"):
            try:
                ai_text = await _generate_ai_event_summary(str(effective_context.get("user_message", "")), result)
                result["ai_recommendation"] = ai_text.strip()
                result.setdefault("data_sources", {})["gemini_used"] = True
            except (GeminiClientError, Exception) as exc:
                result.setdefault("data_sources", {})["gemini_used"] = False
                if strict_live_mode_enabled():
                    result["error"] = f"Events AI recommendation failed: {type(exc).__name__}: {exc}"
            return result

        if isinstance(final_state, dict) and isinstance(result, dict) and result.get("agent") == "events":
            campus_failures = int(final_state.get("campus_failures", 0) or 0)
            nearby_failures = int(final_state.get("nearby_failures", 0) or 0)
            total_web_failures = campus_failures + nearby_failures
            if total_web_failures >= 2:
                gemini_options = await _generate_gemini_event_options(
                    str(effective_context.get("user_message", "")),
                    [str(item) for item in (final_state.get("interested_categories") or ["general"])],
                    final_state.get("date_preference"),
                )
                if gemini_options:
                    result["options"] = [
                        {
                            "name": event.get("name"),
                            "date": event.get("date"),
                            "time": event.get("time"),
                            "location": event.get("location"),
                            "tags": event.get("tags", []),
                            "free_food": bool(event.get("free_food", False)),
                        }
                        for event in gemini_options
                    ]
                    result["event_recommendations"] = result["options"]
                    result.setdefault("data_sources", {})["events"] = "gemini_after_web_failures"
                    result.setdefault("data_sources", {})["gemini_used"] = True
                    result["warning"] = "Live web/API event sources failed repeatedly; Gemini fallback used after retries."
                    return result
    except Exception:
        pass

    return {
        "agent": "events",
        "options": [],
        "error": "No live event data available, and Gemini fallback failed after repeated web/API attempts.",
        "needs_user_input": True,
        "follow_up_questions": [
            "Try a more specific event type (for example career fair, workshop, or concert).",
            "Try again in a few minutes if event sources are temporarily unavailable.",
        ],
    }
