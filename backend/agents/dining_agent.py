from __future__ import annotations

import asyncio
import math
import os
import re
from datetime import datetime
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

DEFAULT_LOCATIONS_URL = "https://dining.umd.edu/locations"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
UMD_CAMPUS_CENTER = (38.9869, -76.9426)

DIETARY_KEYWORDS = {
    "vegan": ["vegan", "plant-based"],
    "vegetarian": ["vegetarian", "veg"],
    "halal": ["halal"],
    "gluten-free": ["gluten free", "gluten-free", "gf"],
    "kosher": ["kosher"],
}

MENU_KEYWORDS = [
    "salad",
    "bowl",
    "chicken",
    "pizza",
    "burger",
    "noodles",
    "rice",
    "seafood",
    "dessert",
    "coffee",
    "breakfast",
    "lunch",
    "dinner",
]

KNOWN_DINING_HALLS = {
    "South Campus Dining": {
        "distance_min": 5,
        "estimated_meal_price": 12.0,
        "dietary_tags": ["vegan", "halal", "gluten-free"],
        "menu_highlights": ["salad", "grill", "rice bowls"],
        "coords": (38.9839, -76.9446),
    },
    "Yahentamitsi Dining Hall": {
        "distance_min": 8,
        "estimated_meal_price": 13.0,
        "dietary_tags": ["vegetarian", "vegan"],
        "menu_highlights": ["global cuisine", "noodles", "protein bowls"],
        "coords": (38.9907, -76.9378),
    },
    "251 North Dining": {
        "distance_min": 8,
        "estimated_meal_price": 10.0,
        "dietary_tags": ["vegetarian"],
        "menu_highlights": ["pizza", "sandwiches", "dessert"],
        "coords": (38.9888, -76.9451),
    },
}


class DiningState(TypedDict, total=False):
    context: dict[str, Any]
    user_message: str
    budget: float | None
    dietary_preferences: list[str]
    menu_preferences: list[str]
    user_location: str | None
    selected_option: str | None
    location_coords: tuple[float, float] | None
    campus_options: list[dict[str, Any]]
    off_campus_options: list[dict[str, Any]]
    ranked_options: list[dict[str, Any]]
    route_preview: dict[str, Any] | None
    needs_user_input: bool
    follow_up_questions: list[str]
    result: dict[str, Any]


def _safe_float(value: object, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _is_open_by_default_hours() -> bool:
    return 7 <= datetime.now().hour <= 22


def _extract_dining_names_from_locations_page(html: str) -> list[str]:
    text = re.sub(r"<[^>]+>", " ", html)
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    found: list[str] = []
    for hall_name in KNOWN_DINING_HALLS:
        if hall_name.lower() in normalized:
            found.append(hall_name)
    return found


def _fetch_live_dining_names() -> list[str]:
    api_url = os.getenv("UMD_DINING_API_URL")
    api_key = os.getenv("UMD_DINING_API_KEY")

    if api_url:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        response = requests.get(api_url, headers=headers, timeout=4)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            names = [str(item.get("name", "")).strip() for item in payload if isinstance(item, dict)]
            return [name for name in names if name]

    response = requests.get(os.getenv("UMD_DINING_LOCATIONS_URL", DEFAULT_LOCATIONS_URL), timeout=4)
    response.raise_for_status()
    return _extract_dining_names_from_locations_page(response.text)


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _extract_budget_from_message(message: str) -> float | None:
    m = re.search(r"\$(\d+(?:\.\d{1,2})?)", message)
    if m:
        return _safe_float(m.group(1), 0.0)
    return None


def _extract_dietary_from_message(message: str) -> list[str]:
    lowered = message.lower()
    found: list[str] = []
    for label, needles in DIETARY_KEYWORDS.items():
        if any(needle in lowered for needle in needles):
            found.append(label)
    return found


def _extract_menu_preferences(message: str) -> list[str]:
    lowered = message.lower()
    return [k for k in MENU_KEYWORDS if k in lowered]


def _geocode_location(location: str) -> tuple[float, float] | None:
    if not location:
        return None
    response = requests.get(
        NOMINATIM_URL,
        params={"q": location, "format": "json", "limit": 1},
        headers={"User-Agent": os.getenv("NOMINATIM_USER_AGENT", "terpai-backend/0.1")},
        timeout=4,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload:
        return None
    return (_safe_float(payload[0].get("lat"), 0.0), _safe_float(payload[0].get("lon"), 0.0))


def _query_overpass_restaurants(lat: float, lon: float, radius_m: int = 2200) -> list[dict[str, Any]]:
    query = f"""
    [out:json][timeout:8];
    (
      node["amenity"~"restaurant|cafe|fast_food"](around:{radius_m},{lat},{lon});
      way["amenity"~"restaurant|cafe|fast_food"](around:{radius_m},{lat},{lon});
    );
    out center 25;
    """
    response = requests.post(OVERPASS_URL, data=query, timeout=8)
    response.raise_for_status()
    payload = response.json()
    return payload.get("elements", []) if isinstance(payload, dict) else []


def _infer_dietary_from_tags(tags: dict[str, Any]) -> list[str]:
    dietary: list[str] = []
    text = " ".join(str(v).lower() for v in tags.values())
    for label, needles in DIETARY_KEYWORDS.items():
        if any(needle in text for needle in needles):
            dietary.append(label)
    return dietary


def _estimate_price_for_off_campus(tags: dict[str, Any]) -> float:
    cuisine = str(tags.get("cuisine", "")).lower()
    if any(x in cuisine for x in ["fine", "steak", "seafood"]):
        return 20.0
    if any(x in cuisine for x in ["pizza", "fast_food", "burger", "sandwich"]):
        return 12.0
    return 15.0


def _build_option(name: str, budget: float | None, source: str = "campus") -> dict[str, Any]:
    defaults = KNOWN_DINING_HALLS.get(
        name,
        {
            "distance_min": 10,
            "estimated_meal_price": 12.0,
            "dietary_tags": [],
            "menu_highlights": [],
            "coords": UMD_CAMPUS_CENTER,
        },
    )
    estimated_price = _safe_float(defaults.get("estimated_meal_price"), 12.0)
    return {
        "name": name,
        "distance_min": int(defaults.get("distance_min", 10)),
        "budget_ok": budget is None or budget >= estimated_price,
        "hours_open": _is_open_by_default_hours(),
        "dietary_tags": list(defaults.get("dietary_tags", [])),
        "menu_highlights": list(defaults.get("menu_highlights", [])),
        "estimated_meal_price": estimated_price,
        "source": source,
        "coords": defaults.get("coords", UMD_CAMPUS_CENTER),
    }


def _fallback_options(budget: float | None) -> list[dict[str, Any]]:
    return [_build_option(name, budget) for name in KNOWN_DINING_HALLS]


def _node_ingest_context(state: DiningState) -> DiningState:
    context = state.get("context", {})
    message = str(context.get("user_message", ""))
    budget_raw = context.get("budget")
    budget = _safe_float(budget_raw, 0.0) if budget_raw is not None else _extract_budget_from_message(message)

    dietary = list(context.get("dietary_restrictions", [])) if context.get("dietary_restrictions") else []
    dietary.extend(_extract_dietary_from_message(message))
    dietary = list(dict.fromkeys([d.lower().strip() for d in dietary if str(d).strip()]))

    menu_preferences = list(context.get("menu_preferences", [])) if context.get("menu_preferences") else []
    menu_preferences.extend(_extract_menu_preferences(message))
    menu_preferences = list(dict.fromkeys([m.lower().strip() for m in menu_preferences if str(m).strip()]))

    user_location = context.get("user_location") or context.get("origin") or context.get("location") or context.get("location_mentioned")
    selected_option = context.get("selected_dining_option") or context.get("selected_option")

    location_coords = None
    if isinstance(user_location, str) and user_location.strip():
        try:
            location_coords = _geocode_location(user_location)
        except Exception:
            location_coords = None

    return {
        "user_message": message,
        "budget": budget,
        "dietary_preferences": dietary,
        "menu_preferences": menu_preferences,
        "user_location": user_location,
        "selected_option": selected_option,
        "location_coords": location_coords,
    }


def _node_fetch_campus_options(state: DiningState) -> DiningState:
    budget = state.get("budget")
    try:
        names = list(dict.fromkeys([n for n in _fetch_live_dining_names() if n]))
    except Exception:
        names = list(KNOWN_DINING_HALLS.keys())
    if not names:
        names = list(KNOWN_DINING_HALLS.keys())
    return {"campus_options": [_build_option(name, budget, source="campus") for name in names]}


def _node_fetch_off_campus_options(state: DiningState) -> DiningState:
    budget = state.get("budget")
    origin = state.get("location_coords") or UMD_CAMPUS_CENTER
    try:
        raw_places = _query_overpass_restaurants(origin[0], origin[1])
    except Exception:
        return {"off_campus_options": []}

    options: list[dict[str, Any]] = []
    for place in raw_places:
        tags = place.get("tags", {}) if isinstance(place, dict) else {}
        name = str(tags.get("name", "")).strip()
        if not name:
            continue

        lat = place.get("lat")
        lon = place.get("lon")
        center = place.get("center", {}) if isinstance(place.get("center"), dict) else {}
        lat = _safe_float(lat if lat is not None else center.get("lat"), 0.0)
        lon = _safe_float(lon if lon is not None else center.get("lon"), 0.0)
        if lat == 0.0 and lon == 0.0:
            continue

        km = _haversine_distance_km(origin[0], origin[1], lat, lon)
        estimated_price = _estimate_price_for_off_campus(tags)
        dietary = _infer_dietary_from_tags(tags)
        cuisines = [c.strip() for c in str(tags.get("cuisine", "")).split(";") if c.strip()]

        options.append(
            {
                "name": name,
                "distance_min": max(2, int(round(km * 12))),
                "budget_ok": budget is None or budget >= estimated_price,
                "hours_open": True,
                "dietary_tags": dietary,
                "menu_highlights": cuisines[:3],
                "estimated_meal_price": estimated_price,
                "source": "off_campus",
                "coords": (lat, lon),
            }
        )

    deduped: dict[str, dict[str, Any]] = {}
    for option in options:
        if option["name"] not in deduped:
            deduped[option["name"]] = option

    return {"off_campus_options": list(deduped.values())[:20]}


def _node_rank_options(state: DiningState) -> DiningState:
    dietary = state.get("dietary_preferences", [])
    menu_preferences = state.get("menu_preferences", [])
    combined = state.get("campus_options", []) + state.get("off_campus_options", [])
    if not combined:
        combined = _fallback_options(state.get("budget"))

    def _score(option: dict[str, Any]) -> float:
        score = 0.0
        if option.get("budget_ok", False):
            score += 2.5
        if dietary:
            overlap = len(set(dietary).intersection(set(option.get("dietary_tags", []))))
            score += overlap * 2.0
        if menu_preferences:
            menu_blob = " ".join(str(x).lower() for x in option.get("menu_highlights", []))
            score += sum(1.5 for pref in menu_preferences if pref in menu_blob)
        score += max(0.0, 2.0 - (float(option.get("distance_min", 30)) / 15.0))
        if option.get("source") == "campus":
            score += 0.5
        return score

    ranked = sorted(combined, key=_score, reverse=True)
    return {"ranked_options": ranked[:12]}


def _node_build_route_preview(state: DiningState) -> DiningState:
    ranked = state.get("ranked_options", [])
    user_location = state.get("user_location")
    selected_name = state.get("selected_option")

    if not ranked:
        return {"route_preview": None, "needs_user_input": False, "follow_up_questions": []}

    selected = None
    if isinstance(selected_name, str) and selected_name.strip():
        selected = next((opt for opt in ranked if opt.get("name") == selected_name), None)
    if selected is None:
        selected = ranked[0]

    if not user_location:
        return {
            "route_preview": {
                "destination": selected.get("name"),
                "map_url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(str(selected.get('name', 'University of Maryland')))}",
            },
            "needs_user_input": True,
            "follow_up_questions": ["Share your current location (or nearest building) to get walking directions."],
        }

    origin_text = str(user_location)
    destination_text = str(selected.get("name", "University of Maryland"))
    map_url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote_plus(origin_text)}"
        f"&destination={quote_plus(destination_text)}"
        "&travelmode=walking"
    )
    return {
        "route_preview": {
            "origin": origin_text,
            "destination": destination_text,
            "map_url": map_url,
        },
        "needs_user_input": False,
        "follow_up_questions": [],
    }


def _node_build_result(state: DiningState) -> DiningState:
    ranked = state.get("ranked_options", [])
    if not ranked:
        ranked = _fallback_options(state.get("budget"))

    options = [
        {
            "name": opt.get("name"),
            "distance_min": int(opt.get("distance_min", 10)),
            "budget_ok": bool(opt.get("budget_ok", False)),
            "hours_open": bool(opt.get("hours_open", True)),
            "dietary_tags": list(opt.get("dietary_tags", [])),
        }
        for opt in ranked
    ]

    menu_recommendations = [
        {
            "name": opt.get("name"),
            "menu_highlights": opt.get("menu_highlights", []),
            "estimated_meal_price": opt.get("estimated_meal_price"),
            "source": opt.get("source"),
        }
        for opt in ranked[:5]
    ]

    result: dict[str, Any] = {
        "agent": "dining",
        "options": options,
        "menu_recommendations": menu_recommendations,
        "recommendation_basis": {
            "budget": state.get("budget"),
            "dietary_preferences": state.get("dietary_preferences", []),
            "menu_preferences": state.get("menu_preferences", []),
        },
    }
    if state.get("route_preview"):
        result["route_preview"] = state["route_preview"]
    if state.get("needs_user_input"):
        result["needs_user_input"] = True
        result["follow_up_questions"] = state.get("follow_up_questions", [])

    return {"result": result}


def _build_graph() -> Any | None:
    if not LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(DiningState)
    graph.add_node("ingest_context", _node_ingest_context)
    graph.add_node("fetch_campus_options", _node_fetch_campus_options)
    graph.add_node("fetch_off_campus_options", _node_fetch_off_campus_options)
    graph.add_node("rank_options", _node_rank_options)
    graph.add_node("build_route_preview", _node_build_route_preview)
    graph.add_node("build_result", _node_build_result)
    graph.set_entry_point("ingest_context")
    graph.add_edge("ingest_context", "fetch_campus_options")
    graph.add_edge("fetch_campus_options", "fetch_off_campus_options")
    graph.add_edge("fetch_off_campus_options", "rank_options")
    graph.add_edge("rank_options", "build_route_preview")
    graph.add_edge("build_route_preview", "build_result")
    graph.add_edge("build_result", END)
    return graph.compile()


DINING_GRAPH = _build_graph()


def _run_without_langgraph(initial_state: DiningState) -> DiningState:
    state: DiningState = dict(initial_state)
    state.update(_node_ingest_context(state))
    state.update(_node_fetch_campus_options(state))
    state.update(_node_fetch_off_campus_options(state))
    state.update(_node_rank_options(state))
    state.update(_node_build_route_preview(state))
    state.update(_node_build_result(state))
    return state


async def run(context: dict) -> dict:
    initial_state: DiningState = {"context": context}

    try:
        if DINING_GRAPH is not None:
            final_state = await asyncio.wait_for(asyncio.to_thread(DINING_GRAPH.invoke, initial_state), timeout=8)
        else:
            final_state = await asyncio.wait_for(asyncio.to_thread(_run_without_langgraph, initial_state), timeout=8)

        result = final_state.get("result") if isinstance(final_state, dict) else None
        if isinstance(result, dict) and result.get("agent") == "dining" and result.get("options"):
            return result
    except Exception:
        pass

    return {
        "agent": "dining",
        "options": [
            {
                "name": option["name"],
                "distance_min": option["distance_min"],
                "budget_ok": option["budget_ok"],
                "hours_open": option["hours_open"],
                "dietary_tags": option["dietary_tags"],
            }
            for option in _fallback_options(None)
        ],
        "needs_user_input": True,
        "follow_up_questions": [
            "Share your current location (or nearest building) to get walking directions.",
            "Share your budget and dietary restrictions for more accurate dining recommendations.",
        ],
    }
