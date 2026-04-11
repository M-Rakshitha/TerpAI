from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timedelta
from typing import Any, TypedDict
from urllib.parse import quote_plus

import requests

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:
    LANGGRAPH_AVAILABLE = False
    END = None
    StateGraph = None

# External APIs
UMD_CALENDAR_API = "https://calendar.umd.edu/live/json/"
EVENTBRITE_API = "https://www.eventbriteapi.com/v3/events/search"
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


def _fetch_live_campus_events() -> list[dict[str, Any]]:
    try:
        response = requests.get(UMD_CALENDAR_API, timeout=4)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            events: list[dict[str, Any]] = []
            for item in payload[:10]:
                if isinstance(item, dict):
                    event_dict = {
                        "name": item.get("title", "").strip(),
                        "date": item.get("start", ""),
                        "time": item.get("time", ""),
                        "location": item.get("location", "University of Maryland"),
                        "url": item.get("url", ""),
                        "tags": item.get("categories", []),
                        "free_food": bool(item.get("free_food", False)),
                        "category": item.get("category", "general"),
                    }
                    if event_dict["name"]:
                        events.append(event_dict)
            return events
    except Exception:
        pass

    # Fallback to known events
    events = []
    for name, details in KNOWN_UMD_EVENTS.items():
        event_date = datetime.now() + timedelta(days=details.get("date_offset_days", 0))
        events.append(
            {
                "name": name,
                "date": event_date.strftime("%Y-%m-%d"),
                "time": details["time"],
                "location": details["location"],
                "url": "",
                "tags": details["tags"],
                "free_food": details["free_food"],
                "category": details["category"],
            }
        )
    return events


def _query_eventbrite_nearby() -> list[dict[str, Any]]:
    api_key = os.getenv("EVENTBRITE_API_KEY")
    if not api_key:
        return []

    try:
        params = {
            "location.latitude": 38.9869,
            "location.longitude": -76.9426,
            "location.address": "College Park, MD",
            "token": api_key,
            "sort_by": "date",
        }
        response = requests.get(EVENTBRITE_API, params=params, timeout=4)
        response.raise_for_status()
        payload = response.json()
        events: list[dict[str, Any]] = []
        for item in payload.get("events", [])[:5]:
            if isinstance(item, dict):
                start = item.get("start", {})
                event_dict = {
                    "name": item.get("name", {}).get("text", "").strip(),
                    "date": start.get("local", ""),
                    "time": start.get("local", "").split("T")[1] if "T" in start.get("local", "") else "TBA",
                    "location": item.get("venue", {}).get("name", "College Park, MD") if isinstance(item.get("venue"), dict) else "College Park, MD",
                    "url": item.get("url", ""),
                    "tags": ["eventbrite", "nearby"],
                    "free_food": "food" in str(item.get("description", "")).lower() or "refreshments" in str(item.get("description", "")).lower(),
                    "category": "nearby",
                }
                if event_dict["name"]:
                    events.append(event_dict)
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
    except Exception:
        events = [
            {
                "name": event_name,
                "date": (datetime.now() + timedelta(days=details["date_offset_days"])).strftime("%Y-%m-%d"),
                "time": details["time"],
                "location": details["location"],
                "url": "",
                "tags": details["tags"],
                "free_food": details["free_food"],
                "category": details["category"],
            }
            for event_name, details in KNOWN_UMD_EVENTS.items()
        ]

    return {"campus_events": events}


def _node_fetch_nearby_events(state: EventsState) -> EventsState:
    try:
        nearby = _query_eventbrite_nearby()
    except Exception:
        nearby = []

    return {"nearby_events": nearby}


def _node_rank_events(state: EventsState) -> EventsState:
    categories = state.get("interested_categories", ["general"])
    dietary = state.get("dietary_preferences", [])
    date_pref = state.get("date_preference") or "today"
    time_pref = state.get("time_preference")
    free_food_only = state.get("free_food_only", False)

    combined = state.get("campus_events", []) + state.get("nearby_events", [])
    if not combined:
        combined = [
            {
                "name": event_name,
                "date": (datetime.now() + timedelta(days=details["date_offset_days"])).strftime("%Y-%m-%d"),
                "time": details["time"],
                "location": details["location"],
                "url": "",
                "tags": details["tags"],
                "free_food": details["free_food"],
                "category": details["category"],
            }
            for event_name, details in KNOWN_UMD_EVENTS.items()
        ]

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
    if not ranked:
        ranked = [
            {
                "name": event_name,
                "date": (datetime.now() + timedelta(days=details["date_offset_days"])).strftime("%Y-%m-%d"),
                "time": details["time"],
                "location": details["location"],
                "url": "",
                "tags": details["tags"],
                "free_food": details["free_food"],
                "category": details["category"],
            }
            for event_name, details in KNOWN_UMD_EVENTS.items()
        ]

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


async def run(context: dict) -> dict:
    initial_state: EventsState = {"context": context}

    try:
        if EVENTS_GRAPH is not None:
            final_state = await asyncio.wait_for(asyncio.to_thread(EVENTS_GRAPH.invoke, initial_state), timeout=8)
        else:
            final_state = await asyncio.wait_for(asyncio.to_thread(_run_without_langgraph, initial_state), timeout=8)

        result = final_state.get("result") if isinstance(final_state, dict) else None
        if isinstance(result, dict) and result.get("agent") == "events" and result.get("options"):
            return result
    except Exception:
        pass

    return {
        "agent": "events",
        "options": [
            {
                "name": event_name,
                "date": (datetime.now() + timedelta(days=details["date_offset_days"])).strftime("%Y-%m-%d"),
                "time": details["time"],
                "location": details["location"],
                "tags": details["tags"],
                "free_food": details["free_food"],
            }
            for event_name, details in KNOWN_UMD_EVENTS.items()
        ],
        "needs_user_input": True,
        "follow_up_questions": [
            "What type of events are you interested in?",
            "When would you like to attend?",
        ],
    }
