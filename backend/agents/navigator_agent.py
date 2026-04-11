from __future__ import annotations

import asyncio
import json
import math
import os
import re
from functools import lru_cache
from typing import Any
from urllib.parse import quote_plus

import requests


MAP_BASE_URL = "https://map.umd.edu/"
MAP_API_URL = "https://map.umd.edu/include/index.php"
DEFAULT_ORIGIN = "McKeldin Library"
DEFAULT_DESTINATION = "Stamp Student Union"
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


def _extract_text_context(context: dict[str, Any]) -> str:
    parts = [
        context.get("user_message"),
        context.get("query"),
        context.get("destination"),
        context.get("location"),
        context.get("building"),
        context.get("place"),
        context.get("target"),
    ]
    return " ".join(str(part) for part in parts if isinstance(part, str) and part.strip())


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

    response = _map_request("getSuggestionsList", json.dumps({"input": query}))
    response.raise_for_status()
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


def _find_building_match(query: str) -> dict[str, Any] | None:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return None

    buildings = _fetch_map_buildings()

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

    if _is_vague_location_query(message):
        suggestions = _fetch_map_suggestions(message)
        for suggestion in suggestions:
            match = _find_building_match(suggestion)
            if match:
                return match["name_long"], match, suggestions[:5]
        if suggestions:
            first_suggestion = suggestions[0]
            return first_suggestion, {"name_long": first_suggestion, "name_short": "", "number": "", "x": UMD_CAMPUS_CENTER[1], "y": UMD_CAMPUS_CENTER[0]}, suggestions[:5]

    return DEFAULT_DESTINATION, _find_building_match(DEFAULT_DESTINATION) or {"name_long": DEFAULT_DESTINATION, "name_short": "", "number": "", "x": UMD_CAMPUS_CENTER[1], "y": UMD_CAMPUS_CENTER[0]}, []


def _resolve_origin(context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    candidates = [context.get("origin"), context.get("start"), context.get("from"), context.get("current_location"), context.get("user_location")]
    origin = next((str(candidate).strip() for candidate in candidates if isinstance(candidate, str) and candidate.strip()), DEFAULT_ORIGIN)
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
    building_token = destination.get("name_short") or destination.get("number") or destination.get("name_long") or DEFAULT_DESTINATION
    if origin:
        origin_text = origin.get("name_short") or origin.get("name_long") or DEFAULT_ORIGIN
        return (
            f"{MAP_BASE_URL}?start={quote_plus(str(origin_text))}"
            f"&stop={quote_plus(str(building_token))}"
        )

    return f"{MAP_BASE_URL}?building={quote_plus(str(building_token))}"


def _build_steps(origin_name: str, destination_name: str, options: list[str]) -> list[str]:
    steps = [
        f"Open the UMD campus map and search for {destination_name}.",
        f"From {origin_name}, head toward {destination_name}.",
        f"Arrive at {destination_name}.",
    ]
    if options:
        steps.append(f"If you meant a different science or engineering building, try: {', '.join(options[:3])}.")
    return steps


async def run(context: dict) -> dict:
    origin_name, origin_building = _resolve_origin(context)
    destination_name, destination_building, suggestions = _resolve_destination(context)

    walk_minutes = _estimate_walk_minutes(origin_building, destination_building)
    map_url = _build_map_url(destination_building, origin_building if origin_name != DEFAULT_ORIGIN or context.get("origin") else None)

    result: dict[str, Any] = {
        "agent": "navigator",
        "origin": origin_name,
        "destination": destination_name,
        "walk_minutes": walk_minutes,
        "steps": _build_steps(origin_name, destination_name, suggestions),
        "map_url": map_url,
    }

    if suggestions:
        result["options"] = suggestions[:5]

    if destination_building.get("name_short") or destination_building.get("number"):
        result["building"] = {
            "number": destination_building.get("number"),
            "name_short": destination_building.get("name_short"),
            "name_long": destination_building.get("name_long"),
            "coords": [destination_building.get("y"), destination_building.get("x")],
        }

    return result