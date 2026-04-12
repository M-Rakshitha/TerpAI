from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
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
UMD_CALENDAR_SEARCH = "https://calendar.umd.edu/search"
EVENTBRITE_SEARCH_URL = "https://www.eventbrite.com/d/md--college-park/events/"
UMD_EVENTS_RSS = "https://news.umd.edu/events/upcoming"
TERPLINK_EVENTS_PAGE = "https://terplink.umd.edu/events"
TERPLINK_EVENTS_RSS = "https://terplink.umd.edu/events.rss"

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
    return list(dict.fromkeys(found))


def _extract_dietary_from_message(message: str) -> list[str]:
    lowered = message.lower()
    found: list[str] = []
    for label, needles in DIETARY_KEYWORDS.items():
        if any(needle in lowered for needle in needles):
            found.append(label)
    return found


def _extract_date_preference(message: str) -> str | None:
    lowered = message.lower()
    iso_match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", lowered)
    if iso_match:
        return f"{iso_match.group(1)}-{iso_match.group(2)}-{iso_match.group(3)}"

    month_match = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:,?\s*(20\d{2}))?\b",
        lowered,
    )
    if month_match:
        month_map = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        month_num = month_map[month_match.group(1)]
        day = int(month_match.group(2))
        year = int(month_match.group(3) or datetime.now().year)
        try:
            return datetime(year, month_num, day).strftime("%Y-%m-%d")
        except ValueError:
            pass

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


def _extract_calendar_events_from_html(html: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()

    for match in re.finditer(r'<a[^>]+href="(?P<url>https://calendar\.umd\.edu/[^"]+)"[^>]*>(?P<title>[^<]+)</a>', html):
        url = str(match.group("url")).strip()
        title = re.sub(r"\s+", " ", str(match.group("title"))).strip()
        if not url or not title:
            continue
        lowered = title.lower()
        if any(noise in lowered for noise in ["university of maryland", "campus calendar", "view event", "additional links", "privacy policy"]):
            continue
        key = f"{title.lower()}::{url}"
        if key in seen:
            continue
        seen.add(key)
        events.append(
            {
                "name": title,
                "date": "",
                "time": "TBA",
                "location": "University of Maryland",
                "url": url,
                "tags": _extract_title_tags(title),
                "free_food": "food" in lowered or "refreshment" in lowered,
                "category": "campus",
            }
        )
        if len(events) >= 20:
            break
    return events


def _fetch_calendar_events_for_date(date_value: str) -> list[dict[str, Any]]:
    try:
        dt = datetime.strptime(date_value, "%Y-%m-%d")
    except ValueError:
        return []
    url = f"{UMD_CALENDAR_HOME}events/{dt.strftime('%Y/%m/%d')}"
    try:
        html = _fetch_html(url)
    except Exception:
        return []

    events = _extract_calendar_events_from_html(html)
    for event in events:
        event["date"] = date_value
    return events


def _fetch_calendar_search_events(query: str) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    try:
        response = requests.get(
            UMD_CALENDAR_SEARCH,
            params={"q": query.strip()},
            timeout=8,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        html = response.text
    except Exception:
        return []

    events = _extract_calendar_events_from_html(html)
    for event in events:
        if not event.get("date"):
            event["date"] = datetime.now().strftime("%Y-%m-%d")
    return events


def _fetch_terplink_events(query: str, date_preference: str | None = None) -> list[dict[str, Any]]:
    try:
        rss = requests.get(TERPLINK_EVENTS_RSS, timeout=8, headers={"User-Agent": "terpai-backend/0.1"})
        rss.raise_for_status()
        root = ET.fromstring(rss.text)
    except Exception:
        return []

    normalized_query = query.lower().strip()
    target_date = date_preference if date_preference and re.match(r"^20\d{2}-\d{2}-\d{2}$", date_preference) else None
    events: list[dict[str, Any]] = []

    for item in root.findall("./channel/item")[:80]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue

        blob = f"{title} {description}".lower()
        if normalized_query and normalized_query not in blob:
            # Keep broad terms by token overlap for computer science / club style queries.
            query_tokens = [token for token in re.split(r"[^a-z0-9]+", normalized_query) if len(token) >= 3]
            if query_tokens and not any(token in blob for token in query_tokens):
                continue

        parsed_date = None
        try:
            parsed_date = datetime.strptime(pub_date[:25], "%a, %d %b %Y %H:%M:%S")
        except Exception:
            parsed_date = datetime.now()
        date_str = parsed_date.strftime("%Y-%m-%d")
        if target_date and date_str != target_date:
            continue

        location_match = re.search(r"located at\s+([^<]+)", description, flags=re.IGNORECASE)
        location = location_match.group(1).strip() if location_match else "University of Maryland"
        time_match = re.search(r"happening on\s+[^\d]*(\d{1,2}:\d{2}\s*[AP]M)", description, flags=re.IGNORECASE)
        time_text = time_match.group(1).strip() if time_match else "TBA"

        events.append(
            {
                "name": title,
                "date": date_str,
                "time": time_text,
                "location": location,
                "url": link,
                "tags": list(dict.fromkeys(["club", *(_extract_title_tags(title))])),
                "free_food": "food" in description.lower() or "snack" in description.lower(),
                "category": "club",
            }
        )
        if len(events) >= 20:
            break

    return events


def _derive_search_query(message: str, categories: list[str]) -> str:
    lowered = message.lower()
    if "computer science" in lowered or "comp sci" in lowered or "cs" in lowered:
        return "computer science"
    if categories:
        return " ".join(categories[:2])
    tokens = [token for token in re.split(r"[^a-z0-9]+", lowered) if len(token) >= 4]
    return " ".join(tokens[:3])


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for event in events:
        name = str(event.get("name", "")).strip().lower()
        date = str(event.get("date", "")).strip()
        if not name:
            continue
        key = f"{name}::{date}"
        if key not in deduped:
            deduped[key] = event
    return list(deduped.values())


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
    message = str(context.get("agent_prompt") or context.get("user_message") or context.get("query") or "").strip()

    if not message:
        return {
            "user_message": "",
            "interested_categories": [],
            "dietary_preferences": [],
            "date_preference": None,
            "time_preference": None,
            "free_food_only": False,
        }

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
    message = str(state.get("user_message", "")).strip()
    categories = state.get("interested_categories", [])
    date_pref = state.get("date_preference")
    query = _derive_search_query(message, categories)

    try:
        events = _fetch_live_campus_events()
        if isinstance(date_pref, str) and re.match(r"^20\d{2}-\d{2}-\d{2}$", date_pref):
            events.extend(_fetch_calendar_events_for_date(date_pref))
        if query:
            events.extend(_fetch_calendar_search_events(query))
        events = _dedupe_events(events)
        failures = 0 if events else 1
    except Exception:
        events = []
        failures = 1

    return {"campus_events": events, "campus_failures": failures}


def _node_fetch_nearby_events(state: EventsState) -> EventsState:
    message = str(state.get("user_message", "")).strip()
    categories = state.get("interested_categories", [])
    date_pref = state.get("date_preference")
    query = _derive_search_query(message, categories)
    try:
        nearby = _query_eventbrite_nearby()
        nearby.extend(_fetch_terplink_events(query, date_pref))
        nearby = _dedupe_events(nearby)
        failures = 0 if nearby else 1
    except Exception:
        nearby = []
        failures = 1

    return {"nearby_events": nearby, "nearby_failures": failures}


def _node_rank_events(state: EventsState) -> EventsState:
    categories = state.get("interested_categories", [])
    dietary = state.get("dietary_preferences", [])
    date_pref = state.get("date_preference")
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
            try:
                event_date = datetime.strptime(date_str, "%Y-%m-%d")
                if event_date.weekday() in (5, 6):
                    score += 2.0
            except Exception:
                pass

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
    message = str(state.get("user_message", "")).strip()
    ranked = state.get("ranked_events", [])

    if not message:
        return {
            "result": {
                "agent": "events",
                "options": [],
                "event_recommendations": [],
                "error": "Events agent requires a clear event request in the prompt.",
                "needs_user_input": True,
                "follow_up_questions": [
                    "What type of events are you looking for (for example workshop, concert, career fair)?",
                    "When do you want to attend (today, tomorrow, weekend, next week)?",
                ],
            }
        }

    if not ranked:
        return {
            "result": {
                "agent": "events",
                "options": [],
                "event_recommendations": [],
                "error": "No live event options could be retrieved from configured sources.",
                "needs_user_input": True,
                "follow_up_questions": [
                    "Try including a specific event type in your prompt.",
                    "Try a time window such as today, tomorrow, or this weekend.",
                ],
            }
        }

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
            "source_url": event.get("url", ""),
        }
        for event in ranked[:5]
    ]

    web_references: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for event in ranked:
        url = str(event.get("url", "")).strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        web_references.append(
            {
                "title": str(event.get("name") or "Event"),
                "url": url,
                "source": str(event.get("source") or "web"),
            }
        )

    needs_input = False
    follow_up: list[str] = []

    if not state.get("interested_categories"):
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
    if web_references:
        result["web_references"] = web_references[:15]

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

        if isinstance(result, dict):
            return result
    except Exception:
        pass

    return {
        "agent": "events",
        "options": [],
        "event_recommendations": [],
        "error": "No live event data available from configured sources.",
        "needs_user_input": True,
        "follow_up_questions": [
            "Try a more specific event type (for example career fair, workshop, or concert).",
            "Try again in a few minutes if event sources are temporarily unavailable.",
        ],
    }
