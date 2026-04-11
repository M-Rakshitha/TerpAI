from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import requests

from backend.utils.ai_workflow import call_gemini_with_retry
from backend.utils.gemini_client import GeminiClientError
from backend.utils.runtime_flags import strict_live_mode_enabled
from backend.utils.student_apis import (
    search_planetterp_professors,
    get_planetterp_professor_info,
    get_umdio_professors,
    format_professor_evidence,
)

DUCKDUCKGO_HTML = "https://duckduckgo.com/html/"

RESOURCE_PROMPT = """
You are a University of Maryland academic support assistant.
Use only the provided live web evidence to produce practical resources.

Return ONLY valid JSON with this shape:
{{
    "tutoring": [
        {{"service": "string", "subject": "string", "schedule": "string", "location": "string"}}
    ],
    "office_hours": [
        {{"professor": "string", "course": "string", "time": "string", "room": "string"}}
    ],
    "resources": [
        {{"name": "string", "category": "tutoring|office_hours|library|advising|study_group|career", "url": "string", "why_useful": "string"}}
    ],
    "advisor_notes": ["string"]
}}

User request: {user_message}
Live web evidence:
{evidence}
""".strip()


def _search_links(query: str, limit: int = 6) -> list[dict]:
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
    results: list[dict] = []
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
        "agent": "study_resources",
        "tutoring": [],
        "office_hours": [],
        "resources": [],
        "advisor_notes": [],
        "error": error,
        "data_sources": {
            "web_search_used": web_used,
            "gemini_used": False,
        },
    }


async def run(context: dict) -> dict:
    course = str(context.get("course", "General Course"))
    user_message = str(context.get("user_message") or context.get("enriched_query") or f"Find UMD resources for {course}")
    
    evidence: list[dict[str, str]] = []

    # Try PlanetTerp API first for professor data (most reliable)
    try:
        planetterp_profs = await search_planetterp_professors(
            query=user_message.strip() or course, limit=5
        )
        if planetterp_profs:
            prof_evidence = await format_professor_evidence(planetterp_profs, "planetterp")
            evidence.extend(prof_evidence)
    except Exception:
        pass

    # Try umd.io API as secondary source
    if len(evidence) < 3:
        try:
            umdio_profs = await get_umdio_professors(limit=5)
            if umdio_profs:
                umdio_evidence = await format_professor_evidence(umdio_profs, "umdio")
                evidence.extend(umdio_evidence[:3 - len(evidence)])
        except Exception:
            pass

    # Fall back to web search for tutoring and general resources
    queries = [
        f"UMD {course} tutoring center",
        f"UMD {course} professor office hours",
        "UMD learning assistance service",
        "UMD writing center tutoring",
        "UMD library subject specialist",
    ]
    search_batches = await asyncio.gather(
        *[asyncio.to_thread(_search_links, query, 4) for query in queries]
    )

    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for batch in search_batches:
        for item in batch:
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            if not title or not url or url in seen:
                continue
            seen.add(url)
            merged.append({"title": title, "url": url})
            if len(merged) >= 10:
                break
        if len(merged) >= 10:
            break

    if not merged and not evidence:
        return _empty_result("No live tutoring/professor resources found", web_used=False)

    snippets = await asyncio.gather(
        *[asyncio.to_thread(_fetch_text_snippet, item["url"]) for item in merged]
    )
    web_evidence = [
        {
            "title": item["title"],
            "url": item["url"],
            "snippet": snippet,
        }
        for item, snippet in zip(merged, snippets)
        if snippet
    ]
    evidence.extend(web_evidence)
    
    if not evidence:
        return _empty_result("Live resource links were found but content could not be retrieved", web_used=True)

    prompt = RESOURCE_PROMPT.format(
        user_message=user_message,
        evidence=json.dumps(evidence[:8]),
    )

    try:
        raw = await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 8)
        parsed = _parse_json(raw)
        tutoring = parsed.get("tutoring", []) if isinstance(parsed, dict) else []
        office_hours = parsed.get("office_hours", []) if isinstance(parsed, dict) else []
        resources = parsed.get("resources", []) if isinstance(parsed, dict) else []
        advisor_notes = parsed.get("advisor_notes", []) if isinstance(parsed, dict) else []

        if not isinstance(tutoring, list) or not isinstance(office_hours, list):
            raise ValueError("Invalid tutoring or office_hours format")
        if not isinstance(resources, list) or not isinstance(advisor_notes, list):
            raise ValueError("Invalid resources or advisor_notes format")

        return {
            "agent": "study_resources",
            "tutoring": tutoring,
            "office_hours": office_hours,
            "resources": resources,
            "advisor_notes": advisor_notes,
            "data_sources": {
                "api_sources": ["planetterp", "umdio", "web_search"],
                "provider": "planetterp+duckduckgo_html",
                "gemini_used": True,
                "web_evidence_count": len(evidence),
            },
        }
    except (GeminiClientError, json.JSONDecodeError, ValueError, Exception) as exc:
        error = f"Study resources generation failed: {type(exc).__name__}: {exc}"
        if strict_live_mode_enabled():
            return _empty_result(error, web_used=True)
        return _empty_result(error, web_used=True)
