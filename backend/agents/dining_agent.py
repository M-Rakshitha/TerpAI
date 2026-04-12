from __future__ import annotations

import asyncio
from collections import deque
from html import unescape
import json
import math
import os
import re
import threading
import time
from datetime import datetime
from typing import Any, TypedDict
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from backend.utils.ai_workflow import call_gemini_with_retry
from backend.utils.runtime_flags import strict_live_mode_enabled
from backend.utils.gemini_client import GeminiClientError

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:
    LANGGRAPH_AVAILABLE = False
    END = None
    StateGraph = None

DEFAULT_LOCATIONS_URL = "https://dining.umd.edu/hours-locations"
DUCKDUCKGO_HTML = "https://duckduckgo.com/html/"
FALLBACK_LOCATIONS_URLS = (
    DEFAULT_LOCATIONS_URL,
    "https://dining.umd.edu/locations",
)
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

try:
    _MAX_EXTERNAL_HTTP_PER_MIN = max(1, int(os.getenv("DINING_HTTP_MAX_REQUESTS_PER_MINUTE", "12")))
except (TypeError, ValueError):
    _MAX_EXTERNAL_HTTP_PER_MIN = 12

try:
    _DINING_PIPELINE_TIMEOUT_SECONDS = max(12.0, float(os.getenv("DINING_PIPELINE_TIMEOUT_SECONDS", "45")))
except (TypeError, ValueError):
    _DINING_PIPELINE_TIMEOUT_SECONDS = 45.0

_HTTP_MIN_INTERVAL_SECONDS = 60.0 / float(_MAX_EXTERNAL_HTTP_PER_MIN)
_HTTP_RATE_LOCK = threading.Lock()
_HTTP_REQUEST_TIMESTAMPS: deque[float] = deque()
_LAST_HTTP_REQUEST_AT = 0.0


def _wait_for_http_rate_slot() -> None:
    global _LAST_HTTP_REQUEST_AT
    # Enforce both rolling-window and spacing constraints across parallel worker threads.
    while True:
        now = time.monotonic()
        with _HTTP_RATE_LOCK:
            while _HTTP_REQUEST_TIMESTAMPS and (now - _HTTP_REQUEST_TIMESTAMPS[0]) >= 60.0:
                _HTTP_REQUEST_TIMESTAMPS.popleft()

            window_wait = 0.0
            if len(_HTTP_REQUEST_TIMESTAMPS) >= _MAX_EXTERNAL_HTTP_PER_MIN:
                window_wait = max(0.0, 60.0 - (now - _HTTP_REQUEST_TIMESTAMPS[0]))

            spacing_wait = max(0.0, (_LAST_HTTP_REQUEST_AT + _HTTP_MIN_INTERVAL_SECONDS) - now)
            delay = max(window_wait, spacing_wait)

            if delay <= 0.0:
                _LAST_HTTP_REQUEST_AT = now
                _HTTP_REQUEST_TIMESTAMPS.append(now)
                return

        time.sleep(min(delay, 1.0) if delay > 0 else 0.01)


def _http_get(url: str, **kwargs: Any) -> requests.Response:
    _wait_for_http_rate_slot()
    return requests.get(url, **kwargs)


def _http_post(url: str, **kwargs: Any) -> requests.Response:
    _wait_for_http_rate_slot()
    return requests.post(url, **kwargs)


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
    web_menu_options: list[dict[str, Any]]
    evidence_options: list[dict[str, Any]]
    campus_source: str
    campus_failures: int
    off_campus_source: str
    off_campus_failures: int
    web_menu_source: str
    web_menu_failures: int
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


def _search_links(query: str, limit: int = 6) -> list[dict[str, str]]:
    try:
        response = _http_get(
            DUCKDUCKGO_HTML,
            params={"q": query},
            timeout=6,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        html = response.text
    except Exception:
        return []

    pattern = re.compile(r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S)
    results: list[dict[str, str]] = []
    for match in pattern.finditer(html):
        title = re.sub(r"<[^>]+>", " ", match.group("title")).strip()
        url = match.group("url").strip()
        if title and url:
            results.append({"title": title, "url": url})
        if len(results) >= limit:
            break
    return results


def _extract_canonical_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        return ""

    if cleaned.startswith("//"):
        cleaned = f"https:{cleaned}"

    parsed = urlparse(cleaned)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        uddg = query.get("uddg")
        if uddg and uddg[0]:
            target = unquote(uddg[0]).strip()
            if target.startswith("http://") or target.startswith("https://"):
                return target
    return cleaned


def _is_probable_restaurant_name(name: str) -> bool:
    normalized = re.sub(r"\s+", " ", name).strip().lower()
    if len(normalized) < 3:
        return False
    banned_exact = {
        "menu",
        "menus",
        "restaurants",
        "food",
        "restaurant",
        "dining",
    }
    if normalized in banned_exact:
        return False
    banned_phrases = [
        "best restaurants",
        "top restaurants",
        "foodies",
        "guide",
        "near me",
        "order online",
    ]
    return not any(phrase in normalized for phrase in banned_phrases)


def _fetch_page_text(url: str) -> str:
    response = _http_get(
        url,
        timeout=6,
        headers={"User-Agent": "terpai-backend/0.1"},
    )
    response.raise_for_status()
    html = response.text
    # Strip script/style/noise first, then tags.
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    text = re.sub(r"(?is)<[^>]+>", " ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_menu_items_with_prices(text: str, budget: float | None, limit: int = 8) -> list[dict[str, Any]]:
    if not text:
        return []

    matches = re.finditer(
        r"([A-Za-z][A-Za-z0-9 '&\-/]{2,60})\s*(?:-|–|:)?\s*\$(\d{1,2}(?:\.\d{1,2})?)",
        text,
    )
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for match in matches:
        item_name = re.sub(r"\s+", " ", match.group(1)).strip(" -:")
        price = _safe_float(match.group(2), 0.0)
        if not item_name or price <= 0:
            continue
        if any(token in item_name.lower() for token in ["copyright", "address", "phone", "open", "hours"]):
            continue
        key = (item_name.lower(), round(price, 2))
        if key in seen:
            continue
        seen.add(key)
        if budget is not None and price > budget:
            continue
        items.append({"item": item_name, "price": round(price, 2)})
        if len(items) >= limit:
            break
    return items


def _name_tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", name.lower()) if len(t) >= 3]


def _result_matches_place_name(title: str, url: str, place_name: str) -> bool:
    blob = f"{title} {url}".lower()
    tokens = _name_tokens(place_name)
    if not tokens:
        return False
    matched = sum(1 for token in tokens if token in blob)
    return matched >= max(1, min(2, len(tokens)))


def _enrich_options_with_web_evidence(
    options: list[dict[str, Any]],
    location: str | None,
    budget: float | None,
    menu_preferences: list[str],
) -> tuple[list[dict[str, Any]], int]:
    enriched: list[dict[str, Any]] = []
    failures = 0
    location_hint = location or "College Park MD"

    for option in options:
        name = str(option.get("name", "")).strip()
        if not name:
            enriched.append(option)
            continue

        search_hits = _search_links(f"{name} {location_hint} menu", limit=6)
        selected_ref: dict[str, str] | None = None
        selected_items: list[dict[str, Any]] = []
        selected_price: float | None = None
        selected_highlights: list[str] = list(option.get("menu_highlights", []))

        for hit in search_hits:
            title = str(hit.get("title", "")).strip()
            url = _extract_canonical_url(str(hit.get("url", "")).strip())
            if not title or not url:
                continue
            if _is_low_quality_listing(title, url, location_hint):
                continue
            if not _result_matches_place_name(title, url, name):
                continue

            try:
                page_text = _fetch_page_text(url)
            except Exception:
                failures += 1
                continue

            items = _extract_menu_items_with_prices(page_text, budget)
            text_blob = f"{title} {url} {page_text[:6000]}"
            price = _extract_price_hint(text_blob)
            if price is None and items:
                avg = sum(float(item["price"]) for item in items) / max(1, len(items))
                price = round(avg, 2)
            if price is None:
                continue

            if not selected_highlights:
                selected_highlights = [pref for pref in menu_preferences if pref in text_blob.lower()]
            if not selected_highlights:
                for token in ["pizza", "bowl", "burger", "salad", "sandwich", "noodles", "taco", "rice"]:
                    if token in text_blob.lower():
                        selected_highlights.append(token)
                selected_highlights = list(dict.fromkeys(selected_highlights))

            selected_ref = {"title": title, "url": url}
            selected_items = items[:6]
            selected_price = float(price)
            break

        updated = dict(option)
        if selected_ref and selected_price is not None:
            updated["web_reference"] = selected_ref
            updated["menu_items_under_budget"] = selected_items
            updated["estimated_meal_price"] = round(selected_price, 2)
            updated["budget_ok"] = budget is None or selected_price <= budget
            updated["menu_highlights"] = selected_highlights[:6]
            if updated.get("source") != "web_menu":
                updated["source"] = "off_campus_web_verified"
        enriched.append(updated)

    return enriched, failures


def _extract_dining_names_from_search_results(results: list[dict[str, str]]) -> list[str]:
    combined = " ".join(f"{item.get('title', '')} {item.get('url', '')}" for item in results).lower()
    found: list[str] = []
    for hall_name in KNOWN_DINING_HALLS:
        if hall_name.lower() in combined:
            found.append(hall_name)
    return found


def _extract_price_hint(text: str) -> float | None:
    lowered = text.lower()
    range_match = re.search(r"\$(\d{1,2})\s*[-to]+\s*\$?(\d{1,2})", lowered)
    if range_match:
        low = _safe_float(range_match.group(1), 0.0)
        high = _safe_float(range_match.group(2), low)
        if low > 0 and high >= low:
            return round((low + high) / 2, 2)
    dollar_signs = lowered.count("$")
    if dollar_signs >= 4:
        return 35.0
    if dollar_signs == 3:
        return 24.0
    if dollar_signs == 2:
        return 16.0
    if dollar_signs == 1:
        return 11.0
    single_price = re.search(r"\$(\d{1,2}(?:\.\d{1,2})?)", lowered)
    if single_price:
        return _safe_float(single_price.group(1), 0.0)
    return None


def _title_to_place_name(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    parts = re.split(r"\s[-|:]\s", cleaned)
    if not parts:
        return cleaned
    candidate = parts[0].strip()
    candidate = re.sub(r"\b(menu|prices|reviews?|order|delivery|college park|umd|restaurants?)\b", "", candidate, flags=re.I)
    candidate = re.sub(r"\s+", " ", candidate).strip(" -|:")
    return candidate or cleaned


def _tokenize_location(text: str | None) -> list[str]:
    if not text:
        return []
    raw_tokens = re.split(r"[^a-z0-9]+", text.lower())
    stopwords = {"the", "and", "near", "at", "from", "of", "university"}
    return [tok for tok in raw_tokens if len(tok) >= 3 and tok not in stopwords]


def _is_location_relevant(title: str, url: str, location_hint: str | None) -> bool:
    blob = f"{title} {url}".lower()
    baseline_tokens = ["college", "park", "umd", "maryland", "cp", "terps"]
    location_tokens = _tokenize_location(location_hint)
    required_tokens = list(dict.fromkeys([*baseline_tokens, *location_tokens]))

    if any(tok in blob for tok in required_tokens):
        return True

    # Explicitly reject common out-of-area artifacts for this UMD use case.
    if any(tok in blob for tok in ["middlebury", "connecticut", "vt 057", "vermont"]):
        return False

    # Many official restaurant pages do not include city/state tokens in title/url.
    # If we don't see explicit out-of-area signals, keep them as potentially relevant.
    return True


def _is_low_quality_listing(title: str, url: str, location_hint: str | None) -> bool:
    blob = f"{title} {url}".lower()
    normalized_title = re.sub(r"\s+", " ", title).strip().lower()
    if any(
        domain in blob
        for domain in [
            "pricelisto.com",
            "menuswithprice.com",
            "allmenus.com",
            "menucollectors.com",
            "restaurantguru.com",
            "grubhub.com",
            "menupix.com",
        ]
    ):
        return True
    if re.match(r"^\d+\s+(best|top)\b", normalized_title):
        return True
    if any(marker in normalized_title for marker in ["best restaurants", "top restaurants", "restaurants for foodies"]):
        return True
    if any(token in blob for token in [".pdf", "/wp-content/", "menupages", "tripadvisor", "opentable"]):
        return True
    if re.search(r"\b(best\s+\d+|top\s+\d+|restaurants?\s+near|foodies|guide\s+to)\b", blob):
        return True
    if any(token in blob for token in ["updated april", "with menus, reviews, photos"]):
        return True
    if not _is_location_relevant(title, url, location_hint):
        return True
    return False


def _build_web_menu_options(location: str | None, budget: float | None, menu_preferences: list[str]) -> tuple[list[dict[str, Any]], str, int]:
    location_hint = location or "Reckord Armory University of Maryland"
    query_set = [
        f"restaurants near {location_hint} menu prices",
        f"site:yelp.com near {location_hint} dinner menu",
        f"site:maps.google.com near {location_hint} restaurants",
        f"site:dining.umd.edu {location_hint} dining hall menu",
    ]
    if menu_preferences:
        query_set.append(f"{' '.join(menu_preferences[:2])} near {location_hint} menu")

    all_hits: list[dict[str, str]] = []
    failures = 0
    for query in query_set:
        hits = _search_links(query, limit=8)
        if hits:
            all_hits.extend(hits)
        else:
            failures += 1

    if not all_hits:
        return [], "none", max(1, failures)

    deduped: dict[str, dict[str, Any]] = {}
    for hit in all_hits:
        title = str(hit.get("title", "")).strip()
        raw_url = str(hit.get("url", "")).strip()
        url = _extract_canonical_url(raw_url)
        if not title or not url:
            continue
        if _is_low_quality_listing(title, url, location_hint):
            continue
        name = _title_to_place_name(title)
        if not name or not _is_probable_restaurant_name(name):
            continue
        if len(name) < 3 or name.lower().startswith("pdf"):
            continue

        try:
            page_text = _fetch_page_text(url)
        except Exception:
            failures += 1
            continue

        text_blob = f"{title} {url} {page_text[:6000]}"
        price = _extract_price_hint(text_blob)
        menu_items_under_budget = _extract_menu_items_with_prices(page_text, budget)
        if price is None and menu_items_under_budget:
            avg = sum(float(item["price"]) for item in menu_items_under_budget) / max(1, len(menu_items_under_budget))
            price = round(avg, 2)
        if price is None:
            # Keep evidence-backed candidates when explicit prices are missing.
            inferred = 14.0 if "menu" in text_blob.lower() or "restaurant" in text_blob.lower() else None
            if inferred is None:
                failures += 1
                continue
            price = inferred

        menu_highlights = [pref for pref in menu_preferences if pref in text_blob.lower()]
        if not menu_highlights:
            for token in ["pizza", "bowl", "burger", "salad", "sandwich", "noodles"]:
                if token in text_blob.lower():
                    menu_highlights.append(token)
            menu_highlights = list(dict.fromkeys(menu_highlights))

        if name not in deduped:
            deduped[name] = {
                "name": name,
                "distance_min": 12,
                "budget_ok": budget is None or budget >= price,
                "hours_open": True,
                "dietary_tags": [],
                "menu_highlights": menu_highlights[:4],
                "estimated_meal_price": round(price, 2),
                "source": "web_menu",
                "web_reference": {"title": title, "url": url},
                "menu_items_under_budget": menu_items_under_budget[:6],
                "menu_evidence_snippet": page_text[:700],
            }

    options = list(deduped.values())[:16]
    return options, "duckduckgo_menu_search", failures


def _fetch_live_dining_names() -> tuple[list[str], str, int]:
    failures = 0
    for page_url in [os.getenv("UMD_DINING_LOCATIONS_URL", DEFAULT_LOCATIONS_URL), *FALLBACK_LOCATIONS_URLS]:
        try:
            response = _http_get(page_url, timeout=3)
            response.raise_for_status()
            names = _extract_dining_names_from_locations_page(response.text)
            if names:
                return names, "umd_locations_page", failures
            failures += 1
        except Exception:
            failures += 1
            continue

    api_url = os.getenv("UMD_DINING_API_URL")
    api_key = os.getenv("UMD_DINING_API_KEY")

    if api_url:
        try:
            headers: dict[str, str] = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            response = _http_get(api_url, headers=headers, timeout=3)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                names = [str(item.get("name", "")).strip() for item in payload if isinstance(item, dict)]
                names = [name for name in names if name]
                if names:
                    return names, "umd_dining_api", failures
                failures += 1
        except Exception:
            failures += 1

    # Last live fallback before strict-mode empty result: web search references to official UMD dining pages.
    try:
        web_results = _search_links("site:dining.umd.edu UMD dining hall", limit=8)
        web_names = _extract_dining_names_from_search_results(web_results)
        if web_names:
            return web_names, "umd_web_search", failures
        failures += 1
    except Exception:
        failures += 1

    return [], "none", failures


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


def _extract_origin_from_message(message: str) -> str | None:
    if not message:
        return None
    patterns = [
        r"\bfrom\b\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})",
        r"\bnear\b\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})",
        r"\baround\b\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})",
        r"\bat\b\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})",
        r"\bby\b\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})",
    ]
    origin: str | None = None
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            origin = match.group(1)
            break
    if not origin:
        return None

    origin = re.sub(
        r"\b(under|below|within|for|with|that|which|who|budget|price|cost|dollar|dollars)\b.*$",
        "",
        origin,
        flags=re.IGNORECASE,
    )
    origin = re.sub(r"\s+\$\d+(?:\.\d{1,2})?.*$", "", origin)
    origin = origin.strip(" .,")
    return origin or None


def _geocode_location(location: str) -> tuple[float, float] | None:
    if not location:
        return None
    response = _http_get(
        NOMINATIM_URL,
        params={"q": location, "format": "json", "limit": 1},
        headers={"User-Agent": os.getenv("NOMINATIM_USER_AGENT", "terpai-backend/0.1")},
        timeout=3,
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
    response = _http_post(OVERPASS_URL, data=query, timeout=5)
    response.raise_for_status()
    payload = response.json()
    return payload.get("elements", []) if isinstance(payload, dict) else []


def _query_nominatim_restaurants(origin_label: str, limit: int = 12) -> list[dict[str, Any]]:
    response = _http_get(
        NOMINATIM_URL,
        params={
            "q": f"restaurants near {origin_label}",
            "format": "json",
            "limit": limit,
        },
        headers={"User-Agent": os.getenv("NOMINATIM_USER_AGENT", "terpai-backend/0.1")},
        timeout=5,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


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


def _estimate_walk_minutes(origin: tuple[float, float], destination: tuple[float, float]) -> int:
    km = _haversine_distance_km(origin[0], origin[1], destination[0], destination[1])
    return max(2, int(round(km * 12)))


def _build_option(
    name: str,
    budget: float | None,
    source: str = "campus",
    origin_coords: tuple[float, float] | None = None,
) -> dict[str, Any]:
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
    coords = defaults.get("coords", UMD_CAMPUS_CENTER)
    distance_min = int(defaults.get("distance_min", 10))
    if source == "campus" and origin_coords is not None and isinstance(coords, tuple) and len(coords) == 2:
        distance_min = _estimate_walk_minutes(origin_coords, coords)

    return {
        "name": name,
        "distance_min": distance_min,
        "budget_ok": budget is None or budget >= estimated_price,
        "hours_open": _is_open_by_default_hours(),
        "dietary_tags": list(defaults.get("dietary_tags", [])),
        "menu_highlights": list(defaults.get("menu_highlights", [])),
        "estimated_meal_price": estimated_price,
        "source": source,
        "coords": coords,
    }


def _node_ingest_context(state: DiningState) -> DiningState:
    context = state.get("context", {})
    message = str(context.get("user_message", ""))
    budget_raw = context.get("budget") or context.get("max_budget") or context.get("budget_limit")
    budget = _safe_float(budget_raw, 0.0) if budget_raw is not None else _extract_budget_from_message(message)

    dietary_context = context.get("dietary_restrictions") or context.get("dietary_preferences") or []
    dietary = list(dietary_context) if dietary_context else []
    dietary.extend(_extract_dietary_from_message(message))
    dietary = list(dict.fromkeys([d.lower().strip() for d in dietary if str(d).strip()]))

    menu_context = context.get("menu_preferences") or context.get("food_preferences") or context.get("cuisine_preferences") or []
    menu_preferences = list(menu_context) if menu_context else []
    menu_preferences.extend(_extract_menu_preferences(message))
    menu_preferences = list(dict.fromkeys([m.lower().strip() for m in menu_preferences if str(m).strip()]))

    user_location = (
        context.get("user_location")
        or context.get("origin")
        or context.get("location")
        or context.get("location_mentioned")
        or _extract_origin_from_message(message)
    )
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
    origin_coords = state.get("location_coords")
    try:
        fetched = _fetch_live_dining_names()
        if isinstance(fetched, tuple) and len(fetched) == 3:
            fetched_names, source, failures = fetched
        else:
            fetched_names, source, failures = [], "unknown", 1
        names = list(dict.fromkeys([n for n in fetched_names if n]))
    except Exception:
        source = "exception"
        names = []
        failures = 3
    if not names and not strict_live_mode_enabled():
        # Non-strict mode fallback: keep planner useful when live campus sources are flaky.
        names = list(KNOWN_DINING_HALLS.keys())
        source = "known_halls_fallback_after_live_failures"
        failures = max(failures, 1)
    return {
        "campus_options": [
            _build_option(name, budget, source="campus", origin_coords=origin_coords)
            for name in names
        ],
        "campus_source": source,
        "campus_failures": failures,
    }


def _node_fetch_off_campus_options(state: DiningState) -> DiningState:
    budget = state.get("budget")
    origin = state.get("location_coords") or UMD_CAMPUS_CENTER
    failures = 0
    try:
        raw_places = _query_overpass_restaurants(origin[0], origin[1])
        source = "overpass"
    except Exception:
        failures += 1
        try:
            origin_label = str(state.get("user_location") or "University of Maryland College Park")
            nominatim_places = _query_nominatim_restaurants(origin_label)
            raw_places = [
                {
                    "lat": place.get("lat"),
                    "lon": place.get("lon"),
                    "tags": {
                        "name": str(place.get("display_name", "")).split(",")[0].strip(),
                        "cuisine": "restaurant",
                    },
                }
                for place in nominatim_places
                if isinstance(place, dict)
                and _is_probable_restaurant_name(str(place.get("display_name", "")).split(",")[0].strip())
                and not _is_low_quality_listing(str(place.get("display_name", "")).split(",")[0].strip(), str(place.get("display_name", "")), origin_label)
            ]
            source = "nominatim_search"
        except Exception:
            failures += 1
            return {"off_campus_options": [], "off_campus_source": "none", "off_campus_failures": failures}

    options: list[dict[str, Any]] = []
    for place in raw_places:
        tags = place.get("tags", {}) if isinstance(place, dict) else {}
        name = str(tags.get("name", "")).strip()
        if not name:
            continue
        if not _is_probable_restaurant_name(name):
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

    if not deduped:
        failures += 1
    return {"off_campus_options": list(deduped.values())[:20], "off_campus_source": source, "off_campus_failures": failures}


def _node_rank_options(state: DiningState) -> DiningState:
    dietary = state.get("dietary_preferences", [])
    menu_preferences = state.get("menu_preferences", [])
    combined = state.get("evidence_options") or (
        state.get("campus_options", []) + state.get("off_campus_options", []) + state.get("web_menu_options", [])
    )

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
        if option.get("source") == "web_menu":
            score += 0.3
        if option.get("web_reference"):
            score += 1.2
        if option.get("menu_items_under_budget"):
            score += 1.5
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
            "web_reference": opt.get("web_reference"),
            "menu_items_under_budget": opt.get("menu_items_under_budget", []),
        }
        for opt in ranked[:5]
    ]

    web_references = [
        opt.get("web_reference")
        for opt in ranked
        if isinstance(opt.get("web_reference"), dict)
    ]

    result: dict[str, Any] = {
        "agent": "dining",
        "options": options,
        "menu_recommendations": menu_recommendations,
        "data_sources": {
            "campus": state.get("campus_source", "unknown"),
            "off_campus": state.get("off_campus_source", "unknown"),
            "web_menu": state.get("web_menu_source", "unknown"),
            "live_web_or_api_only": True,
        },
        "recommendation_basis": {
            "budget": state.get("budget"),
            "dietary_preferences": state.get("dietary_preferences", []),
            "menu_preferences": state.get("menu_preferences", []),
        },
    }
    if web_references:
        result["web_references"] = web_references[:10]
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


async def _generate_ai_recommendation(user_message: str, result: dict[str, Any]) -> str:
    options = result.get("options", []) if isinstance(result.get("options"), list) else []
    menu = result.get("menu_recommendations", []) if isinstance(result.get("menu_recommendations"), list) else []
    top_options = options[:3]
    top_menu = menu[:3]
    prompt = (
        "You are a UMD dining planning assistant. "
        "Given user intent and candidate options, provide a concise recommendation in 2-3 sentences. "
        "Mention one best option and one backup.\n\n"
        f"User query: {user_message}\n"
        f"Top options: {top_options}\n"
        f"Top menu recommendations: {top_menu}\n"
    )
    return await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 4)


async def _generate_gemini_dining_options(
    user_message: str,
    user_location: str | None,
    budget: float | None,
    dietary_preferences: list[str],
    menu_preferences: list[str],
) -> list[dict[str, Any]]:
    prompt = (
        "You are a UMD dining discovery assistant. "
        "Suggest 3 to 5 likely dining choices near campus based on web knowledge. "
        "Return ONLY valid JSON as an array of objects with keys: "
        "name (string), distance_min (integer), hours_open (boolean), dietary_tags (array of strings), estimated_meal_price (number).\n\n"
        f"User query: {user_message}\n"
        f"User location: {user_location or 'not provided'}\n"
        f"Budget: {budget if budget is not None else 'not provided'}\n"
        f"Dietary preferences: {dietary_preferences}\n"
        f"Menu preferences: {menu_preferences}\n"
    )
    raw = await call_gemini_with_retry(
        prompt,
        "gemini-3.1-flash-lite",
        timeout_seconds=6,
        max_attempts=2,
        base_delay_seconds=0.8,
    )
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    parsed: Any
    try:
        parsed = json.loads(cleaned)
    except Exception:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except Exception:
            return []

    if isinstance(parsed, dict):
        candidate = parsed.get("options") or parsed.get("results") or parsed.get("data")
        parsed = candidate if isinstance(candidate, list) else []
    if not isinstance(parsed, list):
        return []

    options: list[dict[str, Any]] = []
    for item in parsed[:5]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        distance_min = max(2, int(_safe_float(item.get("distance_min"), 12)))
        estimated_price = _safe_float(item.get("estimated_meal_price"), 12.0)
        options.append(
            {
                "name": name,
                "distance_min": distance_min,
                "budget_ok": budget is None or budget >= estimated_price,
                "hours_open": bool(item.get("hours_open", True)),
                "dietary_tags": [str(tag).lower() for tag in item.get("dietary_tags", []) if str(tag).strip()],
                "estimated_meal_price": estimated_price,
                "source": "gemini_fallback",
            }
        )
    return options


async def run(context: dict) -> dict:
    effective_context = dict(context)
    if not isinstance(effective_context.get("user_message"), str) or not effective_context.get("user_message"):
        if isinstance(effective_context.get("agent_prompt"), str) and effective_context.get("agent_prompt"):
            effective_context["user_message"] = str(effective_context.get("agent_prompt"))

    initial_state: DiningState = {"context": effective_context}

    async def _run_parallel_pipeline(state: DiningState) -> DiningState:
        working = dict(state)
        working.update(_node_ingest_context(working))

        campus_task = asyncio.to_thread(_node_fetch_campus_options, working)
        off_campus_task = asyncio.to_thread(_node_fetch_off_campus_options, working)
        strict_mode = strict_live_mode_enabled()
        if strict_mode:
            campus_data, off_campus_data = await asyncio.gather(campus_task, off_campus_task)
            web_options: list[dict[str, Any]] = []
            web_source = "skipped_in_strict_mode"
            web_failures = 0
            evidence_options = list(campus_data.get("campus_options", [])) + list(off_campus_data.get("off_campus_options", []))
            evidence_failures = 0
        else:
            web_task = asyncio.to_thread(
                _build_web_menu_options,
                working.get("user_location"),
                working.get("budget"),
                working.get("menu_preferences", []),
            )

            campus_data, off_campus_data, web_payload = await asyncio.gather(campus_task, off_campus_task, web_task)
            web_options, web_source, web_failures = web_payload

            evidence_input = list(campus_data.get("campus_options", [])) + list(off_campus_data.get("off_campus_options", []))
            evidence_options, evidence_failures = await asyncio.to_thread(
                _enrich_options_with_web_evidence,
                evidence_input,
                working.get("user_location"),
                working.get("budget"),
                working.get("menu_preferences", []),
            )

        working.update(campus_data)
        working.update(off_campus_data)
        working.update(
            {
                "web_menu_options": web_options,
                "evidence_options": evidence_options + web_options,
                "web_menu_source": web_source,
                "web_menu_failures": web_failures + evidence_failures,
            }
        )
        working.update(_node_rank_options(working))
        working.update(_node_build_route_preview(working))
        working.update(_node_build_result(working))
        return working

    try:
        final_state = await asyncio.wait_for(_run_parallel_pipeline(initial_state), timeout=_DINING_PIPELINE_TIMEOUT_SECONDS)

        result = final_state.get("result") if isinstance(final_state, dict) else None
        if isinstance(result, dict) and result.get("agent") == "dining" and result.get("options"):
            try:
                ai_text = await _generate_ai_recommendation(str(effective_context.get("user_message", "")), result)
                result["ai_recommendation"] = ai_text.strip()
                result.setdefault("data_sources", {})["gemini_used"] = True
            except (GeminiClientError, Exception) as exc:
                result.setdefault("data_sources", {})["gemini_used"] = False
                result["warning"] = f"Dining recommendation text unavailable ({type(exc).__name__}); returning ranked live options."
            return result

        if isinstance(final_state, dict) and isinstance(result, dict) and result.get("agent") == "dining":
            campus_failures = int(final_state.get("campus_failures", 0) or 0)
            off_campus_failures = int(final_state.get("off_campus_failures", 0) or 0)
            web_menu_failures = int(final_state.get("web_menu_failures", 0) or 0)
            total_web_failures = campus_failures + off_campus_failures + web_menu_failures
            if total_web_failures >= 2:
                gemini_options = await _generate_gemini_dining_options(
                    str(effective_context.get("user_message", "")),
                    effective_context.get("user_location") or effective_context.get("location") or effective_context.get("origin"),
                    _safe_float(effective_context.get("budget"), 0.0) if effective_context.get("budget") is not None else None,
                    [str(item) for item in (effective_context.get("dietary_preferences") or [])],
                    [str(item) for item in (effective_context.get("menu_preferences") or [])],
                )
                if gemini_options:
                    result["options"] = gemini_options
                    result.setdefault("data_sources", {})["campus"] = "gemini_after_web_failures"
                    result.setdefault("data_sources", {})["off_campus"] = "gemini_after_web_failures"
                    result.setdefault("data_sources", {})["gemini_used"] = True
                    result["warning"] = "Live dining web/API sources failed repeatedly; Gemini fallback used after retries."
                    return result
    except Exception:
        pass

    return {
        "agent": "dining",
        "options": [],
        "data_sources": {
            "campus": "none",
            "off_campus": "none",
            "live_web_or_api_only": True,
            "gemini_used": False,
        },
        "error": "No live dining options found, and Gemini fallback could not produce usable results.",
        "needs_user_input": True,
        "follow_up_questions": [
            "Share your current location (or nearest building) to get walking directions.",
            "Share your budget and dietary restrictions for more accurate dining recommendations.",
        ],
    }
