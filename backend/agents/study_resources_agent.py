from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

import requests

from backend.utils.ai_workflow import call_gemini_with_retry
from backend.utils.gemini_client import GeminiClientError
from backend.utils.runtime_flags import strict_live_mode_enabled
from backend.utils.student_apis import (
    search_planetterp_professors,
    get_umdio_professors,
    format_professor_evidence,
)

DUCKDUCKGO_HTML = "https://duckduckgo.com/html/"

STUDY_API_STAGE_TIMEOUT_SECONDS = float(os.getenv("STUDY_API_STAGE_TIMEOUT_SECONDS", "10"))
STUDY_WEB_STAGE_TIMEOUT_SECONDS = float(os.getenv("STUDY_WEB_STAGE_TIMEOUT_SECONDS", "10"))
STUDY_GEMINI_TIMEOUT_SECONDS = float(os.getenv("STUDY_GEMINI_TIMEOUT_SECONDS", "10"))
STUDY_MAX_WEB_QUERIES = int(os.getenv("STUDY_MAX_WEB_QUERIES", "3"))

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
        "web_references": [],
    }


def _extract_professor_name_hint(message: str) -> str | None:
    patterns = [
        r"(?:professor|prof)\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,2})",
        r"office hours for\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1).strip()
    return None


async def run(context: dict) -> dict:
    course = str(context.get("course") or context.get("subject") or "").strip()
    user_message = str(
        context.get("agent_prompt")
        or context.get("user_message")
        or context.get("enriched_query")
        or course
        or ""
    ).strip()

    if not user_message:
        return _empty_result("Study resources agent requires a clear request in the prompt", web_used=False)
    
    evidence: list[dict[str, str]] = []
    seen_titles: set[str] = set()

    def _append_unique(items: list[dict[str, str]], limit: int = 12) -> None:
        for item in items:
            title = str(item.get("title", "")).strip().lower()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            evidence.append(item)
            if len(evidence) >= limit:
                break

    professor_hint = _extract_professor_name_hint(user_message)

    # Prefer UMD professor API first.
    try:
        umdio_profs = await asyncio.wait_for(
            get_umdio_professors(name=professor_hint or None, limit=8),
            timeout=max(3.0, STUDY_API_STAGE_TIMEOUT_SECONDS),
        )
        if umdio_profs:
            umdio_evidence = await format_professor_evidence(umdio_profs, "umdio")
            _append_unique(umdio_evidence)
    except Exception:
        pass

    # Secondary API source: PlanetTerp professor search.
    if len(evidence) < 3:
        try:
            planetterp_profs = await asyncio.wait_for(
                search_planetterp_professors(query=professor_hint or user_message.strip() or course, limit=6),
                timeout=max(3.0, STUDY_API_STAGE_TIMEOUT_SECONDS),
            )
            if planetterp_profs:
                prof_evidence = await format_professor_evidence(planetterp_profs, "planetterp")
                _append_unique(prof_evidence)
        except Exception:
            pass

    # Fall back to web search for tutoring and general resources
    queries = [
        f"site:umd.edu {course or 'computer science'} tutoring",
        f"site:umd.edu {professor_hint or 'professor'} office hours",
        "site:umd.edu learning assistance service",
        "site:umd.edu writing center tutoring",
        "site:umd.edu library subject specialist",
    ]
    queries = queries[: max(1, STUDY_MAX_WEB_QUERIES)]
    try:
        search_batches = await asyncio.wait_for(
            asyncio.gather(*[asyncio.to_thread(_search_links, query, 3) for query in queries]),
            timeout=max(4.0, STUDY_WEB_STAGE_TIMEOUT_SECONDS),
        )
    except Exception:
        search_batches = []

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

    try:
        snippets = await asyncio.wait_for(
            asyncio.gather(*[asyncio.to_thread(_fetch_text_snippet, item["url"]) for item in merged]),
            timeout=max(4.0, STUDY_WEB_STAGE_TIMEOUT_SECONDS),
        )
    except Exception:
        snippets = [""] * len(merged)
    web_evidence = [
        {
            "title": item["title"],
            "url": item["url"],
            "snippet": snippet,
        }
        for item, snippet in zip(merged, snippets)
        if snippet
    ]
    _append_unique(web_evidence)

    web_references = [
        {
            "title": str(item.get("title") or "Resource"),
            "url": str(item.get("url") or ""),
        }
        for item in evidence
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    ]
    
    if not evidence:
        return _empty_result("Live resource links were found but content could not be retrieved", web_used=True)

    prompt = RESOURCE_PROMPT.format(
        user_message=user_message,
        evidence=json.dumps(evidence[:8]),
    )

    try:
        raw = await asyncio.wait_for(
            call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 8),
            timeout=max(5.0, STUDY_GEMINI_TIMEOUT_SECONDS),
        )
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
            "web_references": web_references[:15],
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
        resource_rows = [
            {
                "name": str(item.get("title") or "UMD resource"),
                "category": "library",
                "url": str(item.get("url") or ""),
                "why_useful": "Live search hit; open the page for hours and contact details.",
            }
            for item in evidence[:10]
            if isinstance(item, dict) and str(item.get("url") or "").strip()
        ]
        return {
            "agent": "study_resources",
            "tutoring": [],
            "office_hours": [],
            "resources": resource_rows,
            "advisor_notes": [
                "AI formatting failed; showing direct links from live evidence.",
                error,
            ],
            "web_references": web_references[:15],
            "data_sources": {
                "api_sources": ["planetterp", "umdio", "web_search"],
                "provider": "planetterp+duckduckgo_html",
                "gemini_used": False,
                "web_evidence_count": len(evidence),
            },
            "warning": error,
        }
