from __future__ import annotations

import asyncio
import json
import math
import os
import re
from functools import lru_cache
from typing import Any, TypedDict
from urllib.parse import quote_plus

import requests
from langgraph.graph import END, StateGraph
from backend.utils.runtime_flags import strict_live_mode_enabled
from backend.utils.ai_workflow import call_gemini_with_retry
from backend.utils.gemini_client import GeminiClientError


MAP_BASE_URL = "https://map.umd.edu/"
MAP_API_URL = "https://map.umd.edu/include/index.php"
GOOGLE_MAPS_DIR_URL = "https://www.google.com/maps/dir/?api=1"
GOOGLE_MAPS_SEARCH_URL = "https://www.google.com/maps/search/?api=1"
UMDIO_MAP_BUILDINGS_URL = "https://api.umd.io/v1/map/buildings"
UMD_CAMPUS_CENTER = (38.9869, -76.9426)

NAVIGATION_ALIASES: list[tuple[tuple[str, ...], str]] = [
    (("computer science", "cs", "programming"), "computer science"),
    (("science", "sciences", "science classes", "science building"), "science"),
    (("engineering", "engineer", "stem"), "engineering"),
    (("math", "mathematics", "calculus", "algebra"), "mathematics"),
    (("physics", "physical science"), "physics"),
    (("chemistry", "chem lab", "chem"), "chemistry"),
    (("biology", "bio", "biological"), "biology"),
    (("business", "smith school", "finance"), "business"),
    (("library", "study", "study space", "book"), "library"),
    (("dining", "food", "meal", "eat", "lunch", "dinner"), "dining"),
    (("dorm", "residence", "housing", "res hall"), "housing"),
    (("health", "clinic", "doctor", "wellness"), "health"),
    (("art", "arts", "theater", "music"), "arts"),
]


def _safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_text(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value).lower())
    return re.sub(r"\s+", " ", text).strip()


def _is_vague_location_query(message: str) -> bool:
    lowered = message.lower()
    return any(
        phrase in lowered
        for phrase in ["where is", "where should i go", "where to go", "what building", "which building", "find", "navigate", "directions"]
    )


def _is_generic_destination_reference(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in [
            "current location",
            "determine coordinates",
            "near me",
            "nearby",
            "around me",
            "close by",
            "restaurants near current location",
            "vegan restaurants",
            "restaurant near current location",
        ]
    )


def _build_generic_search_destination(message: str) -> str | None:
    lowered = message.lower()
    dietary_terms = ["vegan", "vegetarian", "halal", "kosher", "gluten free", "gluten-free", "plant based", "plant-based"]
    nearby_terms = ["near me", "nearby", "around me", "close by", "near", "around"]
    if any(term in lowered for term in nearby_terms):
        matched_dietary = next((term for term in dietary_terms if term in lowered), None)
        if matched_dietary:
            return f"{matched_dietary} restaurants near current location"
        if any(term in lowered for term in ["dining", "dinner", "lunch", "breakfast", "food", "eat", "restaurant", "cafe", "options"]):
            return "restaurants near current location"

    if _is_generic_destination_reference(lowered):
        matched_dietary = next((term for term in dietary_terms if term in lowered), None)
        if matched_dietary:
            return f"{matched_dietary} restaurants near current location"
        return "restaurants near current location"

    return None


def _extract_text_context(context: dict[str, Any]) -> str:
    parts = [
        context.get("agent_prompt"),
        context.get("user_message"),
        context.get("query"),
        context.get("destination"),
        context.get("location"),
        context.get("building"),
        context.get("place"),
        context.get("target"),
    ]
    return " ".join(str(part) for part in parts if isinstance(part, str) and part.strip())


def _extract_origin_from_text(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"\bfrom\b\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})", text, re.IGNORECASE)
    if not match:
        return None
    origin = match.group(1).strip(" .,")
    return origin or None


def _is_vague_origin_reference(text: str) -> bool:
    lowered = _normalize_text(text)
    return lowered in {"here", "current location", "my location", "location", "there"}


def _is_vague_destination_reference(text: str) -> bool:
    lowered = _normalize_text(text)
    if not lowered:
        return True
    return any(
        phrase in lowered
        for phrase in [
            "from here",
            "get to",
            "go to",
            "how to get to",
            "where is",
            "current location",
            "near me",
        ]
    )


def _map_request(function_to_call: str, payload: str = "") -> requests.Response:
    return requests.post(
        MAP_API_URL,
        params={"functionToCall": function_to_call},
        data={"input": payload},
        timeout=15,
        headers={"User-Agent": os.getenv("UMD_MAP_USER_AGENT", "terpai-backend/0.1")},
    )


@lru_cache(maxsize=1)
def _fetch_map_buildings() -> list[dict[str, Any]]:
    response = _map_request("getBuildingsList")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []

    buildings: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        name_short = str(item.get("name_short", "")).strip()
        name_long = str(item.get("name_long", "")).strip()
        number = str(item.get("number", "")).strip()
        if not name_long:
            continue

        buildings.append(
            {
                "number": number,
                "name_short": name_short,
                "name_long": name_long,
                "x": _safe_float(item.get("x"), UMD_CAMPUS_CENTER[1]),
                "y": _safe_float(item.get("y"), UMD_CAMPUS_CENTER[0]),
                "search_text": _normalize_text(f"{number} {name_short} {name_long}"),
            }
        )

    return buildings


def _fetch_map_suggestions(query: str) -> list[str]:
    if not query.strip():
        return []

    try:
        response = _map_request("getSuggestionsList", json.dumps({"input": query}))
        response.raise_for_status()
    except Exception:
        return []
    try:
        payload = response.json()
    except Exception:
        return []

    if isinstance(payload, dict):
        result = payload.get("result", [])
        if isinstance(result, list):
            return [str(item).strip() for item in result if str(item).strip()]

    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]

    return []


@lru_cache(maxsize=1)
def _fetch_umdio_buildings() -> list[dict[str, Any]]:
    try:
        response = requests.get(
            UMDIO_MAP_BUILDINGS_URL,
            timeout=8,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    buildings: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name_long = str(item.get("name", "")).strip()
        name_short = str(item.get("code", "")).strip()
        number = str(item.get("id", "")).strip()
        if not name_long:
            continue
        buildings.append(
            {
                "number": number,
                "name_short": name_short,
                "name_long": name_long,
                "x": _safe_float(item.get("long"), UMD_CAMPUS_CENTER[1]),
                "y": _safe_float(item.get("lat"), UMD_CAMPUS_CENTER[0]),
                "search_text": _normalize_text(f"{number} {name_short} {name_long}"),
            }
        )
    return buildings


def _find_building_match(query: str) -> dict[str, Any] | None:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return None

    buildings: list[dict[str, Any]] = []
    try:
        buildings.extend(_fetch_map_buildings())
    except Exception:
        pass
    try:
        buildings.extend(_fetch_umdio_buildings())
    except Exception:
        pass
    if not buildings:
        return None

    for building in buildings:
        if normalized_query == building["search_text"]:
            return building

    for building in buildings:
        if normalized_query in building["search_text"] or building["search_text"] in normalized_query:
            return building

    for suggestion in _fetch_map_suggestions(query):
        normalized_suggestion = _normalize_text(suggestion)
        for building in buildings:
            if normalized_suggestion == building["search_text"]:
                return building
            if normalized_suggestion in building["search_text"] or building["search_text"] in normalized_suggestion:
                return building

    return None


def _infer_category_query(text: str) -> str | None:
    normalized = _normalize_text(text)
    for keywords, query in NAVIGATION_ALIASES:
        if any(keyword in normalized for keyword in keywords):
            return query
    return None


def _candidate_building_names(query: str, limit: int = 5) -> list[str]:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return []

    tokens = [token for token in normalized_query.split() if len(token) >= 3]
    candidates: list[tuple[int, str]] = []
    seen: set[str] = set()

    buildings: list[dict[str, Any]] = []
    try:
        buildings.extend(_fetch_map_buildings())
    except Exception:
        pass
    try:
        buildings.extend(_fetch_umdio_buildings())
    except Exception:
        pass

    for building in buildings:
        name = str(building.get("name_long") or "").strip()
        search_text = str(building.get("search_text") or "").strip()
        if not name or name.lower() in seen:
            continue

        score = 0
        if normalized_query == search_text:
            score += 8
        if normalized_query in search_text:
            score += 6
        if search_text in normalized_query:
            score += 3
        matched_tokens = sum(1 for token in tokens if token in search_text)
        score += matched_tokens

        # Favor library/building terms when the query is a campus landmark lookup.
        if any(term in normalized_query for term in ["library", "hall", "center", "building", "union", "campus"]):
            if any(term in search_text for term in ["library", "hall", "center", "building", "union", "campus"]):
                score += 2

        if score > 0:
            seen.add(name.lower())
            candidates.append((score, name))

    candidates.sort(key=lambda item: (-item[0], item[1].lower()))
    return [name for _, name in candidates[:limit]]


def _resolve_destination(context: dict[str, Any]) -> tuple[str, dict[str, Any], list[str]]:
    explicit_candidates = [
        context.get("destination"),
        context.get("location"),
        context.get("building"),
        context.get("place"),
        context.get("target"),
    ]
    explicit = next((str(candidate).strip() for candidate in explicit_candidates if isinstance(candidate, str) and candidate.strip()), "")

    if explicit:
        match = _find_building_match(explicit)
        if match:
            return match["name_long"], match, []
        explicit_candidates = _candidate_building_names(explicit)
        if explicit_candidates:
            match = _find_building_match(explicit_candidates[0])
            if match:
                return match["name_long"], match, explicit_candidates[:5]
        if not _is_generic_destination_reference(explicit):
            return explicit, {"name_long": explicit, "name_short": "", "number": "", "x": UMD_CAMPUS_CENTER[1], "y": UMD_CAMPUS_CENTER[0]}, []

    message = _extract_text_context(context)
    category_query = _infer_category_query(message)
    if category_query:
        suggestions = _fetch_map_suggestions(category_query)
        if suggestions:
            for suggestion in suggestions:
                match = _find_building_match(suggestion)
                if match:
                    return match["name_long"], match, suggestions[:5]
            first_suggestion = suggestions[0]
            return first_suggestion, {"name_long": first_suggestion, "name_short": "", "number": "", "x": UMD_CAMPUS_CENTER[1], "y": UMD_CAMPUS_CENTER[0]}, suggestions[:5]
        category_candidates = _candidate_building_names(category_query)
        if category_candidates:
            match = _find_building_match(category_candidates[0])
            if match:
                return match["name_long"], match, category_candidates[:5]

    if _is_vague_location_query(message):
        suggestions = _fetch_map_suggestions(message)
        for suggestion in suggestions:
            match = _find_building_match(suggestion)
            if match:
                return match["name_long"], match, suggestions[:5]
        if suggestions:
            first_suggestion = suggestions[0]
            return first_suggestion, {"name_long": first_suggestion, "name_short": "", "number": "", "x": UMD_CAMPUS_CENTER[1], "y": UMD_CAMPUS_CENTER[0]}, suggestions[:5]
        vague_candidates = _candidate_building_names(message)
        if vague_candidates:
            match = _find_building_match(vague_candidates[0])
            if match:
                return match["name_long"], match, vague_candidates[:5]

    generic_destination = _build_generic_search_destination(message)
    if generic_destination:
        generic_candidates = _candidate_building_names(generic_destination)
        if generic_candidates:
            match = _find_building_match(generic_candidates[0])
            if match:
                return match["name_long"], match, generic_candidates[:5]
        return generic_destination, {"name_long": generic_destination, "name_short": "", "number": "", "x": UMD_CAMPUS_CENTER[1], "y": UMD_CAMPUS_CENTER[0]}, []

    return "", {"name_long": "", "name_short": "", "number": "", "x": UMD_CAMPUS_CENTER[1], "y": UMD_CAMPUS_CENTER[0]}, []


def _resolve_origin(context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    extracted_origin = _extract_origin_from_text(_extract_text_context(context))
    current_location_coords = context.get("current_location_coords")
    if isinstance(current_location_coords, dict):
        latitude = current_location_coords.get("latitude")
        longitude = current_location_coords.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            origin = f"{latitude},{longitude}"
            return origin, {"name_long": origin, "name_short": "", "number": "", "x": longitude, "y": latitude}
    candidates = [
        context.get("origin"),
        context.get("start"),
        context.get("from"),
        context.get("current_location"),
        context.get("user_location"),
        extracted_origin,
    ]
    origin = next((str(candidate).strip() for candidate in candidates if isinstance(candidate, str) and candidate.strip()), "")
    match = _find_building_match(origin)
    if match:
        return match["name_long"], match
    return origin, {"name_long": origin, "name_short": "", "number": "", "x": UMD_CAMPUS_CENTER[1], "y": UMD_CAMPUS_CENTER[0]}


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _estimate_walk_minutes(origin: dict[str, Any], destination: dict[str, Any]) -> int:
    origin_lat = _safe_float(origin.get("y"), UMD_CAMPUS_CENTER[0])
    origin_lon = _safe_float(origin.get("x"), UMD_CAMPUS_CENTER[1])
    destination_lat = _safe_float(destination.get("y"), UMD_CAMPUS_CENTER[0])
    destination_lon = _safe_float(destination.get("x"), UMD_CAMPUS_CENTER[1])
    distance_km = _haversine_distance_km(origin_lat, origin_lon, destination_lat, destination_lon)
    return max(4, int(round(distance_km * 12)))


def _build_map_url(destination: dict[str, Any], origin: dict[str, Any] | None = None) -> str:
    destination_text = destination.get("name_long") or destination.get("name_short") or destination.get("number") or "University of Maryland"
    if origin:
        origin_text = origin.get("name_short") or origin.get("name_long") or "current location"
        return f"{GOOGLE_MAPS_DIR_URL}&origin={quote_plus(str(origin_text))}&destination={quote_plus(str(destination_text))}&travelmode=walking"

    return f"{GOOGLE_MAPS_SEARCH_URL}&query={quote_plus(str(destination_text))}"


def _build_steps(origin_name: str, destination_name: str, options: list[str], walk_minutes: int | None = None) -> list[str]:
    steps = [
        f"Start from {origin_name}.",
        f"Follow the Google Maps route to {destination_name}.",
    ]
    if walk_minutes is not None and walk_minutes > 0:
        steps.append(f"Estimated walking time: {walk_minutes} minutes.")
    if options:
        steps.append(f"Other nearby map results: {', '.join(options[:3])}.")
    return steps


def _build_top_results(origin_building: dict[str, Any], candidates: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidates:
        name = str(raw or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        match = _find_building_match(name)
        if match:
            resolved_name = str(match.get("name_long") or name).strip()
            walk_minutes = _estimate_walk_minutes(origin_building, match)
            coords = [match.get("y"), match.get("x")]
            map_url = _build_map_url(match, origin_building)
            location_note = "On-campus destination"
            results.append(
                {
                    "name": resolved_name,
                    "location": location_note,
                    "walk_minutes": walk_minutes,
                    "map_url": map_url,
                    "coordinates": coords,
                }
            )
            continue

        # For non-campus destinations, still provide actionable map links.
        destination = {
            "name_long": name,
            "name_short": "",
            "number": "",
            "x": UMD_CAMPUS_CENTER[1],
            "y": UMD_CAMPUS_CENTER[0],
        }
        results.append(
            {
                "name": name,
                "location": "Nearby search result",
                "walk_minutes": None,
                "map_url": _build_map_url(destination, origin_building),
                "coordinates": None,
            }
        )

        if len(results) >= 5:
            break

    return results[:5]


def _select_route_destination(destination_name: str, top_results: list[dict[str, Any]]) -> tuple[str, dict[str, Any], int | None]:
    if top_results:
        numeric_candidates = [item for item in top_results if isinstance(item.get("walk_minutes"), int)]
        best = min(numeric_candidates, key=lambda item: int(item.get("walk_minutes") or 10**9)) if numeric_candidates else top_results[0]
        selected_name = str(best.get("name") or destination_name).strip() or destination_name
        selected_match = _find_building_match(selected_name)
        if selected_match:
            return selected_name, selected_match, best.get("walk_minutes") if isinstance(best.get("walk_minutes"), int) else None
        fallback = {
            "name_long": selected_name,
            "name_short": "",
            "number": "",
            "x": UMD_CAMPUS_CENTER[1],
            "y": UMD_CAMPUS_CENTER[0],
        }
        return selected_name, fallback, best.get("walk_minutes") if isinstance(best.get("walk_minutes"), int) else None
    return destination_name, {"name_long": destination_name, "name_short": "", "number": "", "x": UMD_CAMPUS_CENTER[1], "y": UMD_CAMPUS_CENTER[0]}, None


async def _generate_ai_navigation_tip(origin_name: str, destination_name: str, walk_minutes: int) -> str:
    prompt = (
        "You are a campus navigation assistant for UMD. "
        "Write a concise 1-2 sentence walking guidance tip with safety/time awareness.\n\n"
        f"Origin: {origin_name}\nDestination: {destination_name}\nEstimated walk minutes: {walk_minutes}\n"
    )
    return await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 4)


class NavState(TypedDict, total=False):
    context: dict[str, Any]
    message: str
    origin_name: str
    destination_name: str
    origin_building: dict[str, Any]
    destination_building: dict[str, Any]
    suggestions: list[str]
    result: dict[str, Any]
    error: str


async def _extract_from_prompt_node(state: NavState) -> NavState:
    context = state.get("context", {})
    message = _extract_text_context(context)
    message = message.strip()

    if not message:
        return {"message": "", "error": "Navigator requires a destination in the user prompt."}

    prompt = (
        "Extract campus navigation intent from the prompt. Return ONLY strict JSON with keys "
        "origin and destination. Use empty strings when unknown.\n\n"
        f"Prompt: {message}\n"
    )

    extracted_origin = ""
    extracted_destination = ""
    try:
        raw = await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 4)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            extracted_origin = str(parsed.get("origin", "")).strip()
            extracted_destination = str(parsed.get("destination", "")).strip()
    except Exception:
        extracted_origin = ""
        extracted_destination = ""

    # Prompt-native fallback extraction when model output is empty.
    if not extracted_origin:
        extracted_origin = _extract_origin_from_text(message) or ""
    if not extracted_destination:
        destination_patterns = [
            r"\bto\b\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})",
            r"\bnear\b\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})",
            r"\bat\b\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})",
            r"\bwhere is\b\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})",
        ]
        for pattern in destination_patterns:
            m = re.search(pattern, message, re.IGNORECASE)
            if m:
                extracted_destination = m.group(1).strip(" .,")
                break

    ctx_origin, _ = _resolve_origin(context)
    ctx_destination, _, _ = _resolve_destination(context)
    has_coords = False
    current_location_coords = context.get("current_location_coords")
    if isinstance(current_location_coords, dict):
        latitude = current_location_coords.get("latitude")
        longitude = current_location_coords.get("longitude")
        has_coords = isinstance(latitude, (int, float)) and isinstance(longitude, (int, float))

    origin_name = ctx_origin if has_coords else (extracted_origin or ctx_origin)
    if _is_vague_origin_reference(origin_name):
        origin_name = ctx_origin
    destination_name = extracted_destination or ctx_destination
    if _is_vague_destination_reference(destination_name) and ctx_destination:
        destination_name = ctx_destination

    if not destination_name:
        return {
            "message": message,
            "origin_name": origin_name,
            "destination_name": "",
            "error": "Navigator could not detect a destination from the prompt.",
        }

    return {
        "message": message,
        "origin_name": origin_name,
        "destination_name": destination_name,
    }


def _resolve_locations_node(state: NavState) -> NavState:
    destination_name = str(state.get("destination_name", "")).strip()
    origin_name = str(state.get("origin_name", "")).strip()

    destination_building = _find_building_match(destination_name) if destination_name else None
    suggestions = _fetch_map_suggestions(destination_name) if destination_name else []
    if not destination_building and suggestions:
        for suggestion in suggestions:
            destination_building = _find_building_match(suggestion)
            if destination_building:
                destination_name = destination_building.get("name_long") or destination_name
                break

    origin_building = _find_building_match(origin_name) if origin_name else None
    if not origin_building:
        origin_building = {
            "name_long": origin_name,
            "name_short": "",
            "number": "",
            "x": UMD_CAMPUS_CENTER[1],
            "y": UMD_CAMPUS_CENTER[0],
        }

    if not destination_building:
        destination_building = {
            "name_long": destination_name,
            "name_short": "",
            "number": "",
            "x": UMD_CAMPUS_CENTER[1],
            "y": UMD_CAMPUS_CENTER[0],
        }

    return {
        "origin_name": origin_name,
        "destination_name": destination_name,
        "origin_building": origin_building,
        "destination_building": destination_building,
        "suggestions": suggestions[:5],
    }


def _validate_node(state: NavState) -> NavState:
    destination_building = state.get("destination_building", {})
    destination_name = str(state.get("destination_name", "")).strip()
    has_precise_destination = bool(destination_building.get("name_short") or destination_building.get("number"))

    if not destination_name:
        return {"error": "Navigator requires a clear destination from the prompt."}

    if not has_precise_destination:
        top_results = _build_top_results(state.get("origin_building", {}), state.get("suggestions", [])[:5])
        selected_destination_name, selected_destination_building, walk_minutes = _select_route_destination(destination_name, top_results)
        return {
            "result": {
                "agent": "navigator",
                "origin": state.get("origin_name", ""),
                "query_destination": destination_name,
                "destination": selected_destination_name,
                "walk_minutes": walk_minutes or (top_results[0].get("walk_minutes") if top_results else 0) or 0,
                "steps": _build_steps(state.get("origin_name", "your location"), selected_destination_name, state.get("suggestions", [])[:5], walk_minutes or None),
                "map_url": _build_map_url(selected_destination_building, state.get("origin_building", {})),
                "options": state.get("suggestions", [])[:5],
                "top_results": top_results,
            },
        }

    return {}


async def _compose_result_node(state: NavState) -> NavState:
    if state.get("result"):
        return {"result": state["result"]}

    origin_name = str(state.get("origin_name", "")).strip()
    destination_name = str(state.get("destination_name", "")).strip()
    message = str(state.get("message", "")).strip()
    origin_building = state.get("origin_building", {})
    destination_building = state.get("destination_building", {})
    suggestions = state.get("suggestions", [])

    if not destination_name:
        return {
            "result": {
                "agent": "navigator",
                "origin": origin_name,
                "destination": "",
                "walk_minutes": 0,
                "steps": [
                    "Navigator could not detect a destination from your prompt.",
                    "Include a destination building name or acronym (for example: AVW, ESJ, STAMP).",
                ],
                "map_url": f"{GOOGLE_MAPS_SEARCH_URL}&query={quote_plus('University of Maryland')}",
                "error": str(state.get("error") or "Destination is required for navigation."),
            }
        }

    fallback_candidates = _candidate_building_names(message or destination_name, 5)
    top_results = _build_top_results(origin_building, (suggestions or fallback_candidates)[:5]) if (suggestions or fallback_candidates) else []
    selected_destination_name, selected_destination_building, selected_walk_minutes = _select_route_destination(destination_name, top_results)
    walk_minutes = selected_walk_minutes if selected_walk_minutes is not None else _estimate_walk_minutes(origin_building, selected_destination_building)
    map_url = _build_map_url(selected_destination_building, origin_building if origin_name else None)

    result: dict[str, Any] = {
        "agent": "navigator",
        "origin": origin_name,
        "query_destination": destination_name,
        "destination": selected_destination_name,
        "walk_minutes": walk_minutes,
        "steps": _build_steps(origin_name or "your location", selected_destination_name, suggestions, walk_minutes),
        "map_url": map_url,
    }

    if suggestions:
        result["options"] = suggestions[:5]
        result["top_results"] = top_results or _build_top_results(origin_building, suggestions[:5])
    elif top_results:
        result["top_results"] = top_results

    if destination_building.get("name_short") or destination_building.get("number"):
        result["building"] = {
            "number": destination_building.get("number"),
            "name_short": destination_building.get("name_short"),
            "name_long": destination_building.get("name_long"),
            "coords": [destination_building.get("y"), destination_building.get("x")],
        }

    try:
        ai_tip = await _generate_ai_navigation_tip(origin_name or "your location", destination_name, walk_minutes)
        result["ai_tip"] = ai_tip.strip()
        result.setdefault("data_sources", {})["gemini_used"] = True
    except (GeminiClientError, Exception) as exc:
        result.setdefault("data_sources", {})["gemini_used"] = False
        if strict_live_mode_enabled():
            result["error"] = f"Navigator AI tip generation failed: {type(exc).__name__}: {exc}"

    return {"result": result}


def _route_after_validate(state: NavState) -> str:
    return "compose_result"


_NAV_GRAPH = None


def _get_nav_graph():
    global _NAV_GRAPH
    if _NAV_GRAPH is not None:
        return _NAV_GRAPH

    graph = StateGraph(NavState)
    graph.add_node("extract_from_prompt", _extract_from_prompt_node)
    graph.add_node("resolve_locations", _resolve_locations_node)
    graph.add_node("validate", _validate_node)
    graph.add_node("compose_result", _compose_result_node)

    graph.set_entry_point("extract_from_prompt")
    graph.add_edge("extract_from_prompt", "resolve_locations")
    graph.add_edge("resolve_locations", "validate")
    graph.add_conditional_edges("validate", _route_after_validate, {"compose_result": "compose_result"})
    graph.add_edge("compose_result", END)

    _NAV_GRAPH = graph.compile()
    return _NAV_GRAPH


async def run(context: dict) -> dict:
    graph = _get_nav_graph()
    state = await graph.ainvoke({"context": context})

    result = state.get("result")
    if isinstance(result, dict):
        return result

    destination_name = str(state.get("destination_name", "")).strip()
    return {
        "agent": "navigator",
        "origin": str(state.get("origin_name", "")).strip(),
        "destination": destination_name,
        "walk_minutes": 0,
        "steps": [
            "Navigator could not build a route from the prompt.",
            "Provide a destination in your query (for example: from AVW to ESJ).",
        ],
        "map_url": f"{GOOGLE_MAPS_SEARCH_URL}&query={quote_plus(destination_name or 'University of Maryland')}",
        "error": str(state.get("error") or "Navigation plan could not be produced from prompt data."),
    }