#!/usr/bin/env python
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import requests

from backend.utils.ai_workflow import call_gemini_with_retry
from backend.utils.gemini_client import GeminiClientError
from backend.utils.runtime_flags import strict_live_mode_enabled

DUCKDUCKGO_HTML = "https://duckduckgo.com/html/"


def _search_links(query: str, limit: int = 6) -> list[dict[str, str]]:
    """Search for job/research links with flexible pattern matching."""
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

    results: list[dict[str, str]] = []
    
    # Try multiple patterns to find links
    patterns = [
        re.compile(r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S),
        re.compile(r'<a[^>]*href="(?P<url>https?://[^"]+)"[^>]*>(?P<title>[^<]+)</a>', re.S),
    ]
    
    for pattern in patterns:
        if results:
            break
        for match in pattern.finditer(html):
            title = re.sub(r"<[^>]+>", " ", match.group("title")).strip()
            url = match.group("url").strip()
            if title and url and len(title) > 5:
                results.append({"title": title, "url": url})
            if len(results) >= limit:
                break
    
    return results


async def _generate_job_tips(context: dict) -> str:
    """Generate student-focused job search and career tips."""
    major = context.get("major", "your field")
    career_goals = context.get("user_message", "internship or research position")
    
    prompt = (
        "You are a career advisor for University of Maryland students. "
        "Provide actionable job search tips for this student.\n\n"
        f"Major/Field: {major}\n"
        f"Goal: {career_goals}\n\n"
        "Provide 3-4 bullet points covering:\n"
        "• Where to find opportunities (Handshake, LinkedIn, department boards, professor labs)\n"
        "• Key skills to highlight in applications for this field\n"
        "• Specific action to take this week (e.g., reach out to professor, update LinkedIn, attend networking event)\n"
        "• Timeline estimate (when to apply for internships, when to expect replies)\n"
        "Be encouraging and specific to UMD CS/engineering/business/science opportunities."
    )
    return await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 6)


async def _generate_research_email(context: dict) -> str:
    """Generate a student-appropriate research email template."""
    major = context.get("major", "your field")
    interests = context.get("user_message", "research opportunities")
    
    prompt = (
        "Write a professional but personable cold email from a UMD undergraduate seeking a research position. "
        "The email should be 4-5 sentences maximum.\n\n"
        f"Student major: {major}\n"
        f"Research interests: {interests}\n\n"
        "Include:\n"
        "• Subject line\n"
        "• Brief intro and specific research interest\n"
        "• Why this professor/lab (mention 1 reason)\n"
        "• Availability and willingness to learn\n"
        "Keep tone professional but friendly. Include a signature.\n"
        "Make it sound like a real student, not a template."
    )
    return await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 6)


async def run(context: dict) -> dict:
    """Find job, internship, and research opportunities for UMD students."""
    
    user_message = str(context.get("user_message", "internship or research position"))
    major = str(context.get("major", ""))
    
    # Parallel searches for different job types
    job_tips: str | None = None
    research_email: str | None = None
    job_tips_error: str | None = None
    research_email_error: str | None = None
    
    # Generate context-aware advice
    try:
        job_tips = await _generate_job_tips(context)
    except (GeminiClientError, Exception) as exc:
        job_tips_error = f"Job tips generation failed: {type(exc).__name__}"
    
    try:
        research_email = await _generate_research_email(context)
    except (GeminiClientError, Exception) as exc:
        research_email_error = f"Research email generation failed: {type(exc).__name__}"
    
    # Search for opportunities in parallel
    search_queries = [
        f"UMD undergraduate {major} internship opportunities Handshake",
        f"UMD {major} student jobs career fair",
        f"University of Maryland {major} research assistant undergraduate",
        f"UMD faculty research lab opportunities {major}",
    ]
    
    search_results = await asyncio.gather(
        *[asyncio.to_thread(_search_links, query, 4) for query in search_queries]
    )
    
    # Organize results
    internship_jobs = search_results[0] + search_results[1]
    research_labs = search_results[2] + search_results[3]
    
    # Remove duplicates
    seen_urls: set[str] = set()
    internship_jobs = [
        item for item in internship_jobs 
        if not (item["url"] in seen_urls or seen_urls.add(item["url"]))
    ]
    research_labs = [
        item for item in research_labs
        if not (item["url"] in seen_urls or seen_urls.add(item["url"]))
    ]
    
    # Format responses (with backward compatibility for tests)
    formatted_jobs = [
        {
            "title": item["title"][:100],
            "link": item["url"],
            "source": "Handshake/Career",
        }
        for item in internship_jobs[:5]
    ]
    
    formatted_labs = [
        {
            "opportunity": item["title"][:100],
            "link": item["url"],
            "source": "Faculty/Research",
        }
        for item in research_labs[:5]
    ]
    
    total_results = len(formatted_jobs) + len(formatted_labs)
    
    # Build response with both new and legacy field names
    cold_email_response = research_email if research_email else job_tips if job_tips else ""
    
    if strict_live_mode_enabled() and total_results == 0:
        return {
            "agent": "jobs_research",
            "jobs": [],  # Legacy field
            "labs": [],  # Legacy field
            "cold_email": cold_email_response,  # Legacy field
            "internships": [],  # New field
            "research_opportunities": [],  # New field
            "job_search_tips": job_tips,
            "research_email_template": research_email,
            "error": "No live job/research opportunities found in web search",
            "suggestion": "Try searching on Handshake directly, reach out to your major's advising office, or attend career fairs",
            "data_sources": {
                "web_search_used": False,
                "search_provider": "duckduckgo_html",
                "gemini_used": bool(job_tips or research_email),
            },
        }
    
    response = {
        "agent": "jobs_research",
        "jobs": formatted_jobs,  # Legacy field
        "labs": formatted_labs,  # Legacy field
        "cold_email": cold_email_response,  # Legacy field
        "internships": formatted_jobs,  # New field
        "research_opportunities": formatted_labs,  # New field
        "job_search_tips": job_tips,
        "research_email_template": research_email,
        "data_sources": {
            "web_search_used": total_results > 0,
            "search_provider": "duckduckgo_html",
            "results_count": total_results,
            "gemini_used": bool(job_tips or research_email),
        },
    }
    
    if job_tips_error or research_email_error:
        errors = [e for e in [job_tips_error, research_email_error] if e]
        if errors and strict_live_mode_enabled():
            response["warning"] = f"Some AI features unavailable: {', '.join(errors)}"
    
    return response
