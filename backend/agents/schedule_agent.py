from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Any

import requests

from backend.utils.ai_workflow import call_gemini_with_retry
from backend.utils.gemini_client import GeminiClientError
from backend.utils.runtime_flags import strict_live_mode_enabled
from backend.utils.student_apis import (
    get_planetterp_courses,
    search_planetterp_courses,
    get_umdio_courses,
    format_course_evidence,
)

DUCKDUCKGO_HTML = "https://duckduckgo.com/html/"


SCHEDULE_PROMPT = """
You are a University of Maryland academic advising assistant.
You MUST use the provided live web evidence to recommend course options.

Return ONLY valid JSON with this shape:
{{
    "recommended_courses": [
        {{
            "course_id": "string",
            "title": "string",
            "term": "string",
            "meeting_times": ["string"],
            "instructor": "string",
            "source_url": "string",
            "why_fit": "string"
        }}
    ],
    "alternate_courses": [
        {{
            "course_id": "string",
            "title": "string",
            "term": "string",
            "meeting_times": ["string"],
            "instructor": "string",
            "source_url": "string",
            "why_fit": "string"
        }}
    ],
    "advising_notes": ["string"],
    "study_blocks": [
        {{"start": "HH:MM", "end": "HH:MM", "subject": "string", "type": "review|practice|reading"}}
    ],
    "next_deadline": {{"title": "string", "due": "ISO-8601 datetime"}}
}}

Student profile: {student_profile}
User request: {user_message}
Live UMD evidence:
{evidence}
""".strip()


def _extract_student_profile(context: dict, user_message: str) -> dict[str, Any]:
    message = user_message.lower()
    major = context.get("major")
    if not major:
        m = re.search(r"major(?:ing)?\s+in\s+([a-zA-Z\s&-]+)", message)
        if m:
            major = m.group(1).strip().title()

    year = context.get("year")
    if not year:
        y = re.search(r"\b(freshman|sophomore|junior|senior|graduate|grad|first-year|second-year|third-year|fourth-year)\b", message)
        if y:
            year = y.group(1)

    time_preferences = context.get("time_preferences")
    if not time_preferences:
        prefs: list[str] = []
        if any(token in message for token in ["morning", "before noon", "am"]):
            prefs.append("morning")
        if any(token in message for token in ["afternoon", "pm", "after lunch"]):
            prefs.append("afternoon")
        if any(token in message for token in ["evening", "night", "late"]):
            prefs.append("evening")
        if "tuesday" in message or "thursday" in message:
            prefs.append("prefers Tu/Th")
        if "monday" in message or "wednesday" in message or "friday" in message:
            prefs.append("prefers M/W/F")
        time_preferences = prefs

    return {
        "major": major,
        "year": year,
        "time_preferences": time_preferences or [],
    }


def _search_links(query: str, limit: int = 6) -> list[dict[str, str]]:
    try:
        response = requests.get(
            DUCKDUCKGO_HTML,
            params={"q": query},
            timeout=7,
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


def _fetch_text_snippet(url: str, max_len: int = 900) -> str:
    try:
        response = requests.get(url, timeout=6, headers={"User-Agent": "terpai-backend/0.1"})
        response.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", response.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_len]
    except Exception:
        return ""


async def _collect_course_evidence(user_message: str, student_profile: dict[str, Any]) -> list[dict[str, str]]:
    major = str(student_profile.get("major") or "University of Maryland")
    evidence: list[dict[str, str]] = []

    # Try PlanetTerp API first (most reliable for UMD courses)
    try:
        planetterp_courses = await search_planetterp_courses(
            query=user_message.strip() or major, limit=6
        )
        if planetterp_courses:
            pt_evidence = await format_course_evidence(planetterp_courses, "planetterp")
            evidence.extend(pt_evidence)
    except Exception:
        pass

    # Try umd.io API as secondary source
    if len(evidence) < 4:
        try:
            umdio_courses = await get_umdio_courses(limit=6)
            if umdio_courses:
                umdio_evidence = await format_course_evidence(umdio_courses, "umdio")
                evidence.extend(umdio_evidence[:4 - len(evidence)])
        except Exception:
            pass

    # Fall back to web search if API sources are insufficient
    if len(evidence) < 3:
        queries = [
            f"UMD Testudo schedule of classes {major}",
            f"site:app.testudo.umd.edu/soc UMD {major} courses",
            f"UMD course catalog {major}",
        ]
        if user_message.strip():
            queries.append(f"UMD schedule {user_message}")

        search_batches = await asyncio.gather(
            *[asyncio.to_thread(_search_links, query, 4) for query in queries]
        )

        merged: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for batch in search_batches:
            for item in batch:
                url = item.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                merged.append(item)
                if len(merged) >= 8:
                    break
            if len(merged) >= 8:
                break

        snippets = await asyncio.gather(
            *[asyncio.to_thread(_fetch_text_snippet, item["url"]) for item in merged]
        )

        for item, snippet in zip(merged, snippets):
            if snippet:
                evidence.append(
                    {
                        "title": item["title"],
                        "url": item["url"],
                        "snippet": snippet,
                    }
                )
                if len(evidence) >= 8:
                    break

    return evidence


def _parse_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


def _empty_result(error: str, web_used: bool) -> dict[str, Any]:
    return {
        "agent": "schedule",
        "recommended_courses": [],
        "alternate_courses": [],
        "advising_notes": [],
        "study_blocks": [],
        "next_deadline": {
            "title": "Unavailable",
            "due": datetime.now().isoformat(),
        },
        "error": error,
        "data_sources": {
            "web_search_used": web_used,
            "gemini_used": False,
        },
    }



async def run(context: dict) -> dict:
    user_message = str(context.get("user_message") or context.get("enriched_query") or "Create a study plan")
    student_profile = _extract_student_profile(context, user_message)

    evidence = await _collect_course_evidence(user_message, student_profile)
    if not evidence:
        return _empty_result("No live UMD course data found for this request", web_used=False)

    prompt = SCHEDULE_PROMPT.format(
        user_message=user_message,
        student_profile=json.dumps(student_profile),
        evidence=json.dumps(evidence[:6]),
    )

    try:
        raw = await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 8)
        parsed = _parse_json(raw)
        recommended_courses = parsed.get("recommended_courses", []) if isinstance(parsed, dict) else []
        alternate_courses = parsed.get("alternate_courses", []) if isinstance(parsed, dict) else []
        advising_notes = parsed.get("advising_notes", []) if isinstance(parsed, dict) else []
        study_blocks = parsed.get("study_blocks", []) if isinstance(parsed, dict) else []
        next_deadline = parsed.get("next_deadline", {}) if isinstance(parsed, dict) else {}

        if (
            isinstance(recommended_courses, list)
            and isinstance(alternate_courses, list)
            and isinstance(advising_notes, list)
            and isinstance(study_blocks, list)
            and isinstance(next_deadline, dict)
            and next_deadline.get("title")
            and next_deadline.get("due")
        ):
            return {
                "agent": "schedule",
                "recommended_courses": recommended_courses,
                "alternate_courses": alternate_courses,
                "advising_notes": advising_notes,
                "study_blocks": study_blocks,
                "next_deadline": next_deadline,
                "data_sources": {
                    "gemini_used": True,
                    "api_sources": ["planetterp", "umdio", "web_search"],
                    "web_evidence_count": len(evidence),
                },
            }
        raise ValueError("Gemini returned invalid advising schema")
    except (GeminiClientError, json.JSONDecodeError, ValueError, Exception) as exc:
        error = f"Schedule generation failed: {type(exc).__name__}: {exc}"
        if strict_live_mode_enabled():
            return _empty_result(error, web_used=True)
        return _empty_result(error, web_used=True)
