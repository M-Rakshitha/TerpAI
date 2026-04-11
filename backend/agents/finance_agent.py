from __future__ import annotations

import asyncio
import re
import statistics
from typing import Any

import requests
from backend.utils.ai_workflow import call_gemini_with_retry
from backend.utils.gemini_client import GeminiClientError
from backend.utils.runtime_flags import strict_live_mode_enabled

DUCKDUCKGO_HTML = "https://duckduckgo.com/html/"

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "dining": ["dining", "food", "lunch", "dinner", "breakfast", "restaurant", "meal", "cafe"],
    "travel": ["travel", "trip", "bus", "metro", "uber", "lyft", "flight", "gas", "parking", "commute"],
    "classes": ["class", "tuition", "course", "textbook", "book", "lab fee", "materials", "subscription"],
    "events": ["event", "club", "concert", "festival", "movie", "ticket", "social"],
    "housing": ["rent", "housing", "apartment", "utilities"],
    "supplies": ["supplies", "school supplies", "notebook", "printer", "printing"],
}

DEFAULT_CATEGORY_BASELINES = {
    "dining": 65.0,
    "travel": 35.0,
    "classes": 40.0,
    "events": 25.0,
    "housing": 110.0,
    "supplies": 20.0,
}

TIMEFRAME_MULTIPLIERS = {
    "daily": 1 / 7,
    "weekly": 1.0,
    "monthly": 4.0,
    "semester": 16.0,
}


def _to_float(value: object, fallback: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _extract_budget(text: str) -> float | None:
    dollar_match = re.search(r"\$(\d+(?:\.\d{1,2})?)", text)
    if dollar_match:
        return _to_float(dollar_match.group(1))

    plain_match = re.search(
        r"(?:under|within|below|max(?:imum)?|budget(?:ed)?(?:\s+of)?|around)\s*\$?\s*(\d{1,4}(?:\.\d{1,2})?)",
        text.lower(),
    )
    if plain_match:
        return _to_float(plain_match.group(1))

    return None


def _extract_timeframe(text: str) -> str:
    lowered = text.lower()
    if "daily" in lowered or "today" in lowered:
        return "daily"
    if "month" in lowered or "monthly" in lowered:
        return "monthly"
    if "semester" in lowered or "term" in lowered:
        return "semester"
    return "weekly"


def _extract_categories(text: str) -> list[str]:
    lowered = text.lower()
    selected: list[str] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            selected.append(category)
    if not selected:
        return ["dining", "travel", "classes", "events"]
    return list(dict.fromkeys(selected))


def _extract_price_points(text: str) -> list[float]:
    matches = re.findall(r"\$\s*(\d+(?:\.\d{1,2})?)", text)
    values = [_to_float(match) for match in matches]
    cleaned = [value for value in values if value is not None and 0 < value <= 3000]
    return [float(v) for v in cleaned]


def _search_web_cost_signals(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search for cost signals from web using multiple pattern matching strategies."""
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

    results: list[dict[str, Any]] = []
    
    # Strategy 1: Try matching result__a with nearby snippet (more flexible)
    pattern1 = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.S,
    )
    
    for match in pattern1.finditer(html):
        title = re.sub(r"<[^>]+>", " ", match.group("title")).strip()
        url = match.group("url").strip()
        if not title or not url:
            continue

        price_points = _extract_price_points(title)
        results.append(
            {
                "title": title,
                "url": url,
                "snippet": title,
                "price_points": price_points,
            }
        )
        if len(results) >= max_results:
            break
    
    # Strategy 2: If no results, try generic link pattern
    if not results:
        pattern2 = re.compile(r'<a[^>]*href="(?P<url>https?://[^"]+)"[^>]*>(?P<title>[^<]+)</a>', re.S)
        for match in pattern2.finditer(html):
            title = match.group("title").strip()
            url = match.group("url").strip()
            if not title or not url or len(title) < 5:
                continue
            
            price_points = _extract_price_points(title)
            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": title,
                    "price_points": price_points,
                }
            )
            if len(results) >= max_results:
                break

    return results


def _estimate_category_cost(category: str, references: list[dict[str, Any]], timeframe: str) -> float:
    price_points: list[float] = []
    for item in references:
        price_points.extend(item.get("price_points", []))

    if price_points:
        base = statistics.median(price_points)
    else:
        base = DEFAULT_CATEGORY_BASELINES.get(category, 30.0)

    multiplier = TIMEFRAME_MULTIPLIERS.get(timeframe, 1.0)
    return round(base * multiplier, 2)


def _build_web_query(category: str, timeframe: str, user_message: str) -> str:
    timeframe_hint = {
        "daily": "daily",
        "weekly": "weekly",
        "monthly": "monthly",
        "semester": "semester",
    }.get(timeframe, "weekly")
    return f"University of Maryland student {category} costs {timeframe_hint} {user_message}".strip()


def _allocation_weights(categories: list[str]) -> dict[str, float]:
    # Keep class-related costs slightly higher by default for student planning.
    default_weights = {
        "dining": 1.2,
        "travel": 0.9,
        "classes": 1.4,
        "events": 0.7,
        "housing": 2.0,
        "supplies": 0.6,
    }
    selected = {category: default_weights.get(category, 1.0) for category in categories}
    total = sum(selected.values()) or 1.0
    return {category: weight / total for category, weight in selected.items()}


def _build_spending_plan(
    categories: list[str],
    timeframe: str,
    budget: float | None,
    web_references: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], float]:
    estimated_total = 0.0
    estimated_by_category: dict[str, float] = {}
    for category in categories:
        estimate = _estimate_category_cost(category, web_references.get(category, []), timeframe)
        estimated_by_category[category] = estimate
        estimated_total += estimate

    weights = _allocation_weights(categories)
    plan: list[dict[str, Any]] = []

    for category in categories:
        if budget is not None:
            recommended = round(budget * weights.get(category, 0.0), 2)
        else:
            recommended = estimated_by_category[category]

        plan.append(
            {
                "category": category,
                "recommended_allocation": recommended,
                "estimated_market_cost": estimated_by_category[category],
                "within_allocation": recommended >= estimated_by_category[category],
                "references": [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                    }
                    for item in web_references.get(category, [])[:3]
                ],
            }
        )

    return plan, round(estimated_total, 2)


def _build_suggestion(plan: list[dict[str, Any]], budget: float | None, estimated_total: float, timeframe: str) -> str:
    over_categories = [item["category"] for item in plan if not item.get("within_allocation", True)]
    if budget is None:
        return (
            f"Estimated {timeframe} spend is about ${estimated_total:.2f}. "
            "Share a target budget to get a tighter allocation plan."
        )
    if not over_categories:
        return (
            f"Your ${budget:.2f} {timeframe} budget is feasible based on current web price signals. "
            "Track actual spend mid-cycle and re-balance if needed."
        )
    categories_text = ", ".join(over_categories)
    return (
        f"Your plan is tight for: {categories_text}. "
        "Consider cheaper alternatives, bundle purchases, or reducing event/travel frequency this cycle."
    )


async def _generate_ai_budget_strategy(
    user_message: str,
    timeframe: str,
    budget: float | None,
    spending_plan: list[dict[str, Any]],
) -> str:
    """Generate student-focused budget strategy with actionable advice."""
    plan_summary = "\n".join([
        f"  - {item['category'].title()}: ${item.get('recommended_allocation', 0):.2f} "
        f"(estimate: ${item.get('estimated_market_cost', 0):.2f})"
        for item in spending_plan[:6]
    ])
    
    prompt = (
        "You are a budget advisor for University of Maryland students. "
        "Provide practical, actionable budgeting advice focusing on student lifestyle and constraints.\n\n"
        f"Student request: {user_message}\n"
        f"Timeframe: {timeframe}\n"
        f"Total budget: ${budget if budget else 'Not specified'}\n"
        f"Spending breakdown:\n{plan_summary}\n\n"
        "Provide a 2-3 sentence strategy including:\n"
        "1. One specific money-saving action (e.g., use student discounts, carpool, meal prep)\n"
        "2. Alert if any category is over-budget\n"
        "3. Recommendation for tracking or adjusting\n"
        "Be encouraging but realistic about college finances."
    )
    return await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 5)


async def run(context: dict) -> dict:
    user_message = str(context.get("user_message") or context.get("enriched_query") or "")
    combined_text = " ".join(
        part
        for part in [
            user_message,
            str(context.get("plan_goal") or ""),
            str(context.get("notes") or ""),
        ]
        if part
    )

    explicit_budget = _to_float(context.get("budget"))
    parsed_budget = _extract_budget(combined_text)
    budget = explicit_budget if explicit_budget is not None else parsed_budget

    timeframe = _extract_timeframe(combined_text)
    categories = _extract_categories(combined_text)

    web_references: dict[str, list[dict[str, Any]]] = {}
    for category in categories:
        query = _build_web_query(category, timeframe, combined_text)
        references = await asyncio.to_thread(_search_web_cost_signals, query)
        web_references[category] = references

    spending_plan, estimated_total = _build_spending_plan(categories, timeframe, budget, web_references)

    weekly_spent = _to_float(context.get("weekly_spent"), 47.5) or 47.5
    # Keep this legacy field for compatibility with existing consumers.
    budget_remaining = (
        round(max(0.0, budget - min(estimated_total, budget)), 2) if budget is not None else round(max(0.0, 100.0 - weekly_spent), 2)
    )

    all_reference_count = sum(len(values) for values in web_references.values())

    if strict_live_mode_enabled() and all_reference_count == 0:
        return {
            "agent": "finance",
            "weekly_spent": round(weekly_spent, 2),
            "budget_remaining": round(max(0.0, (budget or 0.0)), 2),
            "timeframe": timeframe,
            "categories": categories,
            "budget": budget,
            "estimated_total": None,
            "spending_plan": [],
            "web_references": web_references,
            "data_sources": {
                "web_search_used": False,
                "search_provider": "duckduckgo_html",
                "total_reference_hits": 0,
            },
            "error": "No live web cost references available for this query",
            "suggestion": "Try adding more specific categories or retry when web sources are reachable.",
            "follow_up_questions": [
                "Should I narrow this to one category (for example dining only) for better search accuracy?",
            ],
        }

    ai_strategy: str | None = None
    ai_error: str | None = None
    try:
        ai_strategy = await _generate_ai_budget_strategy(combined_text, timeframe, budget, spending_plan)
    except (GeminiClientError, Exception) as exc:
        ai_error = f"Finance AI strategy generation failed: {type(exc).__name__}: {exc}"

    response = {
        "agent": "finance",
        "weekly_spent": round(weekly_spent, 2),
        "budget_remaining": budget_remaining,
        "timeframe": timeframe,
        "categories": categories,
        "budget": budget,
        "estimated_total": estimated_total,
        "spending_plan": spending_plan,
        "web_references": web_references,
        "data_sources": {
            "web_search_used": all_reference_count > 0,
            "search_provider": "duckduckgo_html",
            "total_reference_hits": all_reference_count,
            "gemini_used": ai_strategy is not None,
        },
        "suggestion": _build_suggestion(spending_plan, budget, estimated_total, timeframe),
        "follow_up_questions": [
            "Do you want this optimized for cheapest options or shortest walking/transit time?",
            "Should I rebalance with strict caps by category (for example dining <= 40% of total)?",
        ],
    }
    if ai_strategy is not None:
        response["ai_strategy"] = ai_strategy.strip()
    if ai_error is not None and strict_live_mode_enabled():
        response["error"] = ai_error
    return response
