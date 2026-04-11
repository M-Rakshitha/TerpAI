"""
Integration utilities for student-run APIs: PlanetTerp and umd.io.
Includes caching with 5-10min TTL and request pacing to respect rate limits.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional
import requests

# ============================================================================
# REQUEST PACING & CACHING
# ============================================================================

# Simple in-memory cache with TTL (5-10 min depending on endpoint)
_cache: dict[str, tuple[Any, float]] = {}
_last_api_call_time: dict[str, float] = {}

# Rate limit delays (respect PlanetTerp's polite request)
REQUEST_PACE_DELAY = 0.3  # 300ms between requests


def _is_cache_valid(key: str, ttl_seconds: int = 600) -> bool:
    """Check if cache entry exists and hasn't expired (default 10 min TTL)."""
    if key not in _cache:
        return False
    _, timestamp = _cache[key]
    return (time.time() - timestamp) < ttl_seconds


def _get_cached(key: str, ttl_seconds: int = 600) -> Optional[Any]:
    """Retrieve cached value if valid (respects TTL)."""
    if _is_cache_valid(key, ttl_seconds):
        value, _ = _cache[key]
        return value
    return None


def _set_cached(key: str, value: Any) -> None:
    """Store value in cache with current timestamp."""
    _cache[key] = (value, time.time())


async def _pace_request(api_name: str) -> None:
    """
    Sleep to respect rate limits between requests to same API.
    Tracks last call time per API name.
    """
    current_time = time.time()
    if api_name in _last_api_call_time:
        elapsed = current_time - _last_api_call_time[api_name]
        if elapsed < REQUEST_PACE_DELAY:
            await asyncio.sleep(REQUEST_PACE_DELAY - elapsed)
    _last_api_call_time[api_name] = time.time()


# ============================================================================
# PLANETTERP API
# ============================================================================

PLANETTERP_BASE = "https://api.planetterp.com/v1"


async def search_planetterp_courses(
    query: str, limit: int = 8
) -> list[dict[str, Any]]:
    """
    Search PlanetTerp for courses matching query (e.g., "MATH140", "Calculus").
    Returns list of course dicts with department, number, title, credits, description.
    """
    cache_key = f"planetterp_courses:{query}:{limit}"
    cached = _get_cached(cache_key, ttl_seconds=600)
    if cached is not None:
        return cached

    await _pace_request("planetterp")
    try:
        # PlanetTerp /search endpoint returns results for courses and professors
        response = requests.get(
            f"{PLANETTERP_BASE}/search",
            params={"query": query},
            timeout=5,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        data = response.json()

        # Filter to courses only
        courses = data.get("courses", []) if isinstance(data, dict) else []
        results = courses[:limit]
        _set_cached(cache_key, results)
        return results
    except Exception:
        return []


async def get_planetterp_courses(
    department: Optional[str] = None, limit: int = 10
) -> list[dict[str, Any]]:
    """
    Get courses from PlanetTerp, optionally filtered by department (e.g., "MATH", "COMP").
    Returns course dicts with department, number, title, credits.
    """
    cache_key = f"planetterp_dept_courses:{department}:{limit}"
    cached = _get_cached(cache_key, ttl_seconds=600)
    if cached is not None:
        return cached

    await _pace_request("planetterp")
    try:
        # PlanetTerp /courses endpoint returns all courses; filter client-side if needed
        response = requests.get(
            f"{PLANETTERP_BASE}/courses",
            timeout=5,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        courses = response.json() if isinstance(response.json(), list) else []

        if department:
            courses = [c for c in courses if c.get("department") == department.upper()]

        results = courses[:limit]
        _set_cached(cache_key, results)
        return results
    except Exception:
        return []


async def get_planetterp_professor_info(
    professor_name: str,
) -> Optional[dict[str, Any]]:
    """
    Get professor info from PlanetTerp by name/slug.
    Returns dict with name, slug, average_rating, courses, reviews.
    """
    cache_key = f"planetterp_prof:{professor_name}"
    cached = _get_cached(cache_key, ttl_seconds=600)
    if cached is not None:
        return cached

    await _pace_request("planetterp")
    try:
        # Normalize name to slug format (lowercase, dashes)
        slug = professor_name.lower().replace(" ", "-")
        response = requests.get(
            f"{PLANETTERP_BASE}/professors/{slug}",
            timeout=5,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        data = response.json()
        _set_cached(cache_key, data)
        return data
    except Exception:
        return None


async def search_planetterp_professors(
    query: str, limit: int = 5
) -> list[dict[str, Any]]:
    """
    Search PlanetTerp for professors matching query (e.g., "David Mount").
    Returns list of professor dicts with name, slug, average_rating.
    """
    cache_key = f"planetterp_prof_search:{query}:{limit}"
    cached = _get_cached(cache_key, ttl_seconds=600)
    if cached is not None:
        return cached

    await _pace_request("planetterp")
    try:
        response = requests.get(
            f"{PLANETTERP_BASE}/search",
            params={"query": query},
            timeout=5,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        data = response.json()
        professors = data.get("professors", []) if isinstance(data, dict) else []
        results = professors[:limit]
        _set_cached(cache_key, results)
        return results
    except Exception:
        return []


async def get_planetterp_grades(
    course_id: str, professor_slug: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    Get historical grade data from PlanetTerp for a course.
    Optionally filtered by professor slug.
    Returns list of grade records with average GPA, semester (YYYYMM format), count.
    """
    cache_key = f"planetterp_grades:{course_id}:{professor_slug}"
    cached = _get_cached(cache_key, ttl_seconds=600)
    if cached is not None:
        return cached

    await _pace_request("planetterp")
    try:
        params = {}
        if professor_slug:
            params["professor"] = professor_slug
        response = requests.get(
            f"{PLANETTERP_BASE}/grades?course_id={course_id}",
            params=params,
            timeout=5,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        grades = response.json() if isinstance(response.json(), list) else []
        _set_cached(cache_key, grades)
        return grades
    except Exception:
        return []


# ============================================================================
# UMD.IO API
# ============================================================================

UMDIO_BASE = "https://api.umd.io/v1"


async def get_umdio_courses(
    course_id: Optional[str] = None, limit: int = 10
) -> list[dict[str, Any]]:
    """
    Get courses from umd.io, optionally filtered by course_id (e.g., "MATH140").
    Returns course data with department, number, title, credits, offered, professors.
    """
    cache_key = f"umdio_courses:{course_id}:{limit}"
    cached = _get_cached(cache_key, ttl_seconds=600)
    if cached is not None:
        return cached

    await _pace_request("umdio")
    try:
        params = {}
        if course_id:
            params["course_id"] = course_id
        response = requests.get(
            f"{UMDIO_BASE}/courses",
            params=params,
            timeout=5,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        courses = response.json() if isinstance(response.json(), list) else []
        results = courses[:limit]
        _set_cached(cache_key, results)
        return results
    except Exception:
        return []


async def get_umdio_professors(
    name: Optional[str] = None, limit: int = 5
) -> list[dict[str, Any]]:
    """
    Get professors from umd.io, optionally filtered by name.
    Returns professor data with name, slug, office, phone, email.
    """
    cache_key = f"umdio_profs:{name}:{limit}"
    cached = _get_cached(cache_key, ttl_seconds=600)
    if cached is not None:
        return cached

    await _pace_request("umdio")
    try:
        params = {}
        if name:
            params["name"] = name
        response = requests.get(
            f"{UMDIO_BASE}/professors",
            params=params,
            timeout=5,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        professors = response.json() if isinstance(response.json(), list) else []
        results = professors[:limit]
        _set_cached(cache_key, results)
        return results
    except Exception:
        return []


async def get_umdio_buildings(
    name: Optional[str] = None, limit: int = 10
) -> list[dict[str, Any]]:
    """
    Get UMD buildings from umd.io map data.
    Returns building data with number, name, abbreviation, latitude, longitude.
    """
    cache_key = f"umdio_buildings:{name}:{limit}"
    cached = _get_cached(cache_key, ttl_seconds=600)
    if cached is not None:
        return cached

    await _pace_request("umdio")
    try:
        params = {}
        if name:
            params["name"] = name
        response = requests.get(
            f"{UMDIO_BASE}/map",
            params=params,
            timeout=5,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        buildings = response.json() if isinstance(response.json(), list) else []
        results = buildings[:limit]
        _set_cached(cache_key, results)
        return results
    except Exception:
        return []


async def get_umdio_majors(limit: int = 50) -> list[dict[str, Any]]:
    """
    Get all UMD majors from umd.io.
    Returns major data with name, college, type.
    """
    cache_key = "umdio_majors_all"
    cached = _get_cached(cache_key, ttl_seconds=3600)  # Cache majors for 1 hour
    if cached is not None:
        return cached

    await _pace_request("umdio")
    try:
        response = requests.get(
            f"{UMDIO_BASE}/majors",
            timeout=5,
            headers={"User-Agent": "terpai-backend/0.1"},
        )
        response.raise_for_status()
        majors = response.json() if isinstance(response.json(), list) else []
        results = majors[:limit]
        _set_cached(cache_key, results)
        return results
    except Exception:
        return []


# ============================================================================
# HELPER FUNCTIONS FOR AGENTS
# ============================================================================


async def format_course_evidence(
    courses: list[dict[str, Any]], source: str
) -> list[dict[str, str]]:
    """
    Convert course list into evidence format for Gemini prompts.
    source: "planetterp" or "umdio"
    """
    evidence: list[dict[str, str]] = []
    for course in courses[:8]:
        dept = course.get("department", "")
        num = course.get("number", "")
        title = course.get("title", "")
        credits = course.get("credits", "")
        description = course.get("description", "")[:200]

        evidence.append(
            {
                "title": f"{dept} {num}: {title}",
                "url": f"https://api.planetterp.com/v1" if source == "planetterp" else f"https://api.umd.io/v1",
                "snippet": f"{description} ({credits} credits)" if description else f"({credits} credits)",
            }
        )
    return evidence


async def format_professor_evidence(
    professors: list[dict[str, Any]], source: str
) -> list[dict[str, str]]:
    """
    Convert professor list into evidence format for Gemini prompts.
    source: "planetterp" or "umdio"
    """
    evidence: list[dict[str, str]] = []
    for prof in professors[:6]:
        name = prof.get("name") or prof.get("slug", "Unknown")
        rating = prof.get("average_rating", "N/A")
        courses = prof.get("courses", [])
        courses_str = ", ".join(courses[:3]) if isinstance(courses, list) else ""

        evidence.append(
            {
                "title": f"Prof. {name}",
                "url": f"https://api.planetterp.com/v1" if source == "planetterp" else f"https://api.umd.io/v1",
                "snippet": f"Rating: {rating}/5. Teaches: {courses_str}" if rating != "N/A" else f"Teaches: {courses_str}",
            }
        )
    return evidence


def clear_cache() -> None:
    """Clear all cached API responses (useful for testing)."""
    global _cache, _last_api_call_time
    _cache.clear()
    _last_api_call_time.clear()
