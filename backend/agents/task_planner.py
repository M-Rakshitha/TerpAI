from __future__ import annotations

import asyncio
import json
import re
from typing import Any, TypedDict

from backend.models.schemas import TaskPlannerContext, TaskPlannerResponse
from backend.utils.ai_workflow import call_gemini_with_retry
from backend.utils.gemini_client import GeminiClientError, call_gemini

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:
    LANGGRAPH_AVAILABLE = False
    END = None
    StateGraph = None

# Step 1: Rewrite user message in descriptive format
MESSAGE_ENRICHMENT_PROMPT = """
You are TerpAI's message enrichment system. Your job is to take a student's brief query and 
rewrite it in a clear, descriptive format that captures their full intent and context.

RULES:
1. Preserve all original intent and constraints
2. Add inferred context (if they say "under $15", infer budget constraint)
3. Expand abbreviations and unclear terms
4. Extract important details like dates, locations, amounts 
5. Keep it concise but explicit
6. If the query is dietary shorthand (e.g., "vegan options near me"), rewrite it as a dining request near the user's current location.

User query: {user_message}

Rewritten query (1-2 sentences, very descriptive):
""".strip()

# Step 2: Task router - determines which agents to activate
TASK_PLANNER_PROMPT = """
You are TerpAI's task router for University of Maryland students.
Given a descriptive rewrite of what the student needs, identify which agents should be activated in PARALLEL:

Available agents (activate zero or more):
- schedule: Course schedules, exam dates, deadlines, class conflicts, assignments
- dining: Finding food, dining halls, restaurants, meal preferences, dietary restrictions
- events: Finding events, clubs, workshops, seminars, social activities
- finance: Budgeting, spending analysis, financial goals, account tracking
- navigator: Building locations, walking directions, campus maps, transportation
- study_resources: Tutoring, office hours, study groups, academic help, Q&A resources
- jobs_research: Job/internship search, research opportunities, career development, resume help

ANALYSIS INSTRUCTIONS:
1. Identify each student need from the query
2. For each need, select THE MOST RELEVANT agent (only one per need)
3. Consider that multiple agents can run in PARALLEL (no ordering)
4. Extract constraint values: budget amounts, deadlines, locations, etc.
5. Determine priority based on urgency (deadline, exam date, etc.)
6. Activate schedule ONLY for explicit academic planning/course/time-table requests.
7. Activate study_resources ONLY for explicit requests for tutoring/professors/office hours/resources.
8. If no agent is clearly required, return an empty tasks array.
9. Dietary-food queries (vegan/vegetarian/halal/gluten-free/kosher + food/options/place to eat) map to dining.
10. "near me" or location-based dining requests should include navigator for route support.

Query: {enriched_message}

Return ONLY this JSON format (no markdown, no explanation):
{{
  "tasks": ["agent1", "agent2"],
  "priority": "high",
  "enriched_query": "{enriched_message}",
  "context": {{
    "budget": null,
    "deadline_mentioned": false,
    "location_mentioned": null,
    "extracted_constraints": {{}}
  }},
  "parallel_groups": ["all"],
  "reasoning": "Brief one-line explanation"
}}

Return ONLY valid JSON, no other text.
""".strip()


DIETARY_TERMS = [
    "vegan",
    "vegetarian",
    "halal",
    "kosher",
    "gluten free",
    "gluten-free",
    "plant based",
    "plant-based",
]


NEARBY_LOCATION_TERMS = [
    "near me",
    "nearby",
    "near me?",
    "around me",
    "close by",
    "closest",
    "near",
    "around",
    "by me",
]


def _fallback_enrich_message(user_message: str) -> str:
    """Fallback message enrichment using simple rules."""
    enhance = f"User needs: {user_message}"
    
    # Add inferred context
    if re.search(r"\$\d+", user_message):
        budget_match = re.search(r"\$(\d+)", user_message)
        if budget_match:
            enhance += f" | Budget constraint: under ${budget_match.group(1)}"
    
    if any(k in user_message.lower() for k in ["tomorrow", "today", "tonight"]):
        enhance += " | Time-sensitive query"
    
    if any(k in user_message.lower() for k in ["near", "at", "location", "where"]):
        location_match = re.search(r"near\s+(\w+)|\s+at\s+(\w+)", user_message)
        if location_match:
            loc = location_match.group(1) or location_match.group(2)
            enhance += f" | Location context: {loc}"

    lowered = user_message.lower()
    if any(term in lowered for term in DIETARY_TERMS):
        enhance += " | Dining intent with dietary constraints"
        if "near me" in lowered:
            enhance += " | Use current user location"
    
    return enhance


def _normalize_enriched_message(text: str, fallback: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("text"):
            cleaned = cleaned[4:].strip()
    cleaned = re.sub(r"^\s*rewritten\s+query\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or fallback


def _fallback_plan(user_message: str, enriched_message: str = "") -> TaskPlannerResponse:
    """Fallback task routing using keyword matching."""
    if not enriched_message:
        enriched_message = _fallback_enrich_message(user_message)
    
    text = user_message.lower()
    combined_text = f"{user_message} {enriched_message}".lower()
    tasks: list[str] = []
    constraints: dict[str, Any] = {}

    budget_terms = {
        "low": 80,
        "budget-friendly": 100,
        "cheap": 80,
        "affordable": 120,
    }

    # Keyword-based agent activation
    if any(k in text for k in ["exam", "deadline", "study", "assignment", "quiz", "class", "schedule"]):
        tasks.append("schedule")
    if any(k in combined_text for k in ["eat", "dining", "food", "lunch", "dinner", "breakfast", "restaurant", "cafe", "meal", "options", "place to eat"]):
        tasks.append("dining")
    if "coffee" in combined_text:
        tasks.append("dining")
    if any(term in combined_text for term in DIETARY_TERMS):
        tasks.append("dining")
    if any(k in text for k in ["event", "club", "workshop", "seminar", "talk", "concert", "movie"]):
        tasks.append("events")
    if any(
        k in text
        for k in [
            "budget",
            "$",
            "spend",
            "finance",
            "money",
            "cost",
            "price",
            "plan",
            "afford",
            "cheap",
            "cheapest",
            "save",
            "under",
            "within",
        ]
    ):
        tasks.append("finance")
        budget_match = re.search(r"\$(\d+)", user_message)
        if budget_match:
            constraints["budget"] = int(budget_match.group(1))
        else:
            alt_budget_match = re.search(
                r"(?:under|within|below|max(?:imum)?|budget(?:ed)?(?:\s+of)?|around)\s*\$?\s*(\d{1,4})",
                user_message.lower(),
            )
            if alt_budget_match:
                constraints["budget"] = int(alt_budget_match.group(1))
            else:
                for token, value in budget_terms.items():
                    if token in text:
                        constraints["budget"] = value
                        break
    if any(
        k in text
        for k in [
            "where is",
            "get to",
            "how do i get to",
            "navigate",
            "directions",
            "walk to",
            "map",
            "location",
            "building",
            "library",
            "route me",
            "route me there",
            "get me there",
            "take me there",
        ]
    ):
        tasks.append("navigator")
        location_match = re.search(
            r"(?:\bnear\b|\bat\b|\blocate\b|\bfrom\b)\s+([a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80})",
            user_message,
            re.IGNORECASE,
        )
        if location_match:
            loc = location_match.group(1).strip(" .,")
            constraints["location"] = loc
    if any(term in combined_text for term in DIETARY_TERMS) and any(term in combined_text for term in NEARBY_LOCATION_TERMS):
        if "dining" not in tasks:
            tasks.append("dining")
        if "navigator" not in tasks:
            tasks.append("navigator")
    if any(k in text for k in ["tutor", "office hours", "study resources", "help", "learn", "quiet study", "study spot", "study spots"]):
        tasks.append("study_resources")
    if any(k in text for k in ["job", "internship", "research", "lab", "resume", "career", "hiring"]):
        tasks.append("jobs_research")

    tasks = _enforce_precise_agent_activation(tasks, user_message, enriched_message)
    tasks = _enforce_navigation_intent(tasks, user_message, enriched_message)
    tasks = _enforce_finance_intent(tasks, user_message, enriched_message)

    deadline_mentioned = any(k in text for k in ["tomorrow", "deadline", "due", "exam", "quiz", "today", "tonight", "urgent"])
    
    location_mentioned = constraints.get("location", None)

    return TaskPlannerResponse(
        tasks=tasks,
        priority="high" if deadline_mentioned else "medium",
        context=TaskPlannerContext(
            budget=constraints.get("budget"),
            deadline_mentioned=deadline_mentioned,
            location_mentioned=location_mentioned,
        ),
    )


def _parse_planner_json(raw: str) -> TaskPlannerResponse:
    """Parse Gemini response into TaskPlannerResponse."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try extracting the first JSON object from mixed model output.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1])
    tasks = data.get("tasks", [])
    priority = data.get("priority", "medium")
    
    context_data = data.get("context", {})
    budget_value = context_data.get("budget")
    if isinstance(budget_value, str):
        budget_match = re.search(r"(\d+(?:\.\d{1,2})?)", budget_value)
        budget_value = float(budget_match.group(1)) if budget_match else None
    elif not isinstance(budget_value, (int, float)):
        budget_value = None

    context = TaskPlannerContext(
        budget=budget_value,
        deadline_mentioned=context_data.get("deadline_mentioned", False),
        location_mentioned=context_data.get("location_mentioned"),
    )
    
    return TaskPlannerResponse(
        tasks=tasks,
        priority=priority,
        context=context,
    )


class PlannerGraphState(TypedDict, total=False):
    user_message: str
    enriched_message: str
    tasks: list[str]
    priority: str
    context: dict[str, Any]
    ai_enrichment_used: bool
    ai_routing_used: bool
    ai_error: str | None


def _node_enrich_message(state: PlannerGraphState) -> PlannerGraphState:
    user_message = state.get("user_message", "")
    prompt = MESSAGE_ENRICHMENT_PROMPT.format(user_message=user_message)
    fallback = _fallback_enrich_message(user_message)
    try:
        enriched = call_gemini(prompt, "gemini-3.1-flash-lite", 4).strip()
        enriched = _normalize_enriched_message(enriched, fallback)
        return {
            "enriched_message": enriched or fallback,
            "ai_enrichment_used": bool(enriched and enriched != fallback),
        }
    except Exception:
        return {
            "enriched_message": fallback,
            "ai_enrichment_used": False,
        }


def _node_route_tasks(state: PlannerGraphState) -> PlannerGraphState:
    user_message = state.get("user_message", "")
    enriched_message = state.get("enriched_message") or _fallback_enrich_message(user_message)
    prompt = TASK_PLANNER_PROMPT.format(enriched_message=enriched_message)
    try:
        raw = call_gemini(prompt, "gemini-3.1-flash-lite", 6)
        parsed = _parse_planner_json(raw)
        if not parsed.tasks and any(term in enriched_message.lower() for term in DIETARY_TERMS):
            recovery_prompt = (
                TASK_PLANNER_PROMPT.format(enriched_message=enriched_message)
                + "\nImportant: This request includes dietary constraints and is actionable. Select at least one agent if possible."
            )
            recovery_raw = call_gemini(recovery_prompt, "gemini-3.1-flash-lite", 6)
            recovery_parsed = _parse_planner_json(recovery_raw)
            if recovery_parsed.tasks:
                parsed = recovery_parsed
        return {
            "tasks": parsed.tasks,
            "priority": parsed.priority,
            "context": parsed.context.model_dump(),
            "ai_routing_used": True,
            "ai_error": None,
        }
    except Exception as exc:
        fallback = _fallback_plan(user_message, enriched_message)
        return {
            "tasks": fallback.tasks,
            "priority": fallback.priority,
            "context": fallback.context.model_dump(),
            "ai_routing_used": False,
            "ai_error": f"{type(exc).__name__}: {exc}",
        }


def _build_planner_graph() -> Any | None:
    if not LANGGRAPH_AVAILABLE:
        return None
    graph = StateGraph(PlannerGraphState)
    graph.add_node("enrich", _node_enrich_message)
    graph.add_node("route", _node_route_tasks)
    graph.set_entry_point("enrich")
    graph.add_edge("enrich", "route")
    graph.add_edge("route", END)
    return graph.compile()


PLANNER_GRAPH = _build_planner_graph()


def _enforce_navigation_intent(tasks: list[str], user_message: str, enriched_message: str) -> list[str]:
    combined_text = f"{user_message} {enriched_message}".lower()
    navigation_intent = any(
        token in combined_text
        for token in [
            "route me",
            "route me there",
            "get me there",
            "take me there",
            "directions",
            "navigate",
            "walk to",
        ]
    )
    dining_intent = any(
        token in combined_text
        for token in [
            "dining",
            "dinner",
            "lunch",
            "breakfast",
            "restaurant",
            "cafe",
            "where to eat",
            "food",
            "meal",
            "vegan",
            "vegetarian",
            "halal",
            "gluten-free",
            "gluten free",
        ]
    )
    location_qualified = bool(
        re.search(
            r"\b(near|around|at|from|by)\b\s+[a-zA-Z0-9][a-zA-Z0-9 .'-]{1,80}",
            f"{user_message} {enriched_message}",
            re.IGNORECASE,
        )
    )

    should_add_navigator = navigation_intent or (dining_intent and location_qualified)
    if should_add_navigator and "navigator" not in tasks:
        tasks = [*tasks, "navigator"]
    return list(dict.fromkeys(tasks))


def _enforce_finance_intent(tasks: list[str], user_message: str, enriched_message: str) -> list[str]:
    combined_text = f"{user_message} {enriched_message}".lower()
    original_text = user_message.lower()
    explicit_finance_terms = any(
        token in combined_text
        for token in [
            "spend",
            "spending",
            "finance",
            "money",
            "cost breakdown",
            "allocation",
            "weekly",
            "monthly",
            "semester",
            "save",
            "afford",
        ]
    )
    planning_terms = any(token in combined_text for token in ["plan", "track", "optimize", "rebalance", "breakdown", "manage"])
    budget_present = bool(re.search(r"\$\s*\d+", combined_text)) or any(
        token in combined_text for token in ["under", "within", "max", "maximum", "budget"]
    )
    student_spending_domains = any(
        token in combined_text
        for token in ["dining", "food", "travel", "class", "tuition", "textbook", "events", "supplies", "rent"]
    )
    dining_only_intent = student_spending_domains and any(
        token in combined_text for token in ["dinner", "lunch", "breakfast", "where to eat", "restaurant", "cafe"]
    ) and not any(
        token in combined_text for token in ["track", "weekly", "monthly", "spending", "rebalance", "allocation"]
    )

    pure_dining_place_query = any(
        token in original_text
        for token in [
            "what to have for dinner",
            "where to eat",
            "dinner near",
            "lunch near",
            "breakfast near",
            "restaurant near",
            "food near",
        ]
    ) and not any(
        token in original_text
        for token in [
            "budget plan",
            "spending plan",
            "weekly",
            "monthly",
            "allocation",
            "track",
            "finance",
            "save",
            "afford",
        ]
    )

    if (explicit_finance_terms and student_spending_domains) or (planning_terms and student_spending_domains and budget_present):
        tasks = [*tasks, "finance"]

    # Do not force finance for straightforward dining-place requests that merely include a price cap.
    if dining_only_intent:
        tasks = [task for task in tasks if task != "finance"]

    if budget_present and planning_terms and student_spending_domains:
        tasks = [*tasks, "finance"]

    # Hard guard: pure dining-place queries with a simple price cap should not invoke finance.
    if pure_dining_place_query:
        tasks = [task for task in tasks if task != "finance"]

    return list(dict.fromkeys(tasks))


def _enforce_precise_agent_activation(tasks: list[str], user_message: str, enriched_message: str) -> list[str]:
    original_text = user_message.lower()
    combined_text = f"{user_message} {enriched_message}".lower()

    schedule_intent = any(
        token in combined_text
        for token in [
            "course",
            "schedule plan",
            "weekly schedule",
            "class schedule",
            "classes",
            "what should i take",
            "which courses",
            "time preference",
            "major",
            "semester plan",
            "exam",
            "deadline",
            "assignment due",
        ]
    )
    study_resources_intent = any(
        token in combined_text
        for token in [
            "tutor",
            "tutoring",
            "office hours",
            "professor",
            "study resources",
            "academic support",
            "writing center",
            "learning assistance",
            "study group",
        ]
    )
    events_intent = any(
        token in original_text
        for token in [
            "event",
            "events",
            "workshop",
            "seminar",
            "club",
            "concert",
            "festival",
            "career fair",
        ]
    )
    dining_place_intent = any(
        token in original_text
        for token in [
            "dining",
            "dinner",
            "lunch",
            "breakfast",
            "coffee",
            "restaurant",
            "cafe",
            "where to eat",
            "meal",
            "food options",
            "place to eat",
            "vegan",
            "vegetarian",
            "halal",
            "gluten-free",
            "gluten free",
        ]
    )
    finance_intent = any(
        token in combined_text
        for token in [
            "budget",
            "money",
            "cost",
            "price",
            "spend",
            "spending",
            "expense",
            "financial",
            "afford",
            "savings",
            "save",
            "under $",
        ]
    )

    filtered = list(dict.fromkeys(tasks))
    if "schedule" in filtered and not schedule_intent:
        filtered = [task for task in filtered if task != "schedule"]
    if "study_resources" in filtered and not study_resources_intent:
        filtered = [task for task in filtered if task != "study_resources"]
    if "dining" in filtered and events_intent and not dining_place_intent:
        filtered = [task for task in filtered if task != "dining"]
    if "finance" in filtered and not finance_intent:
        filtered = [task for task in filtered if task != "finance"]

    dietary_dining_intent = any(term in combined_text for term in DIETARY_TERMS) and any(
        token in combined_text for token in ["options", "places", "place", "food", "eat", "eatery", "restaurant", "cafe", "meal"]
    )
    nearby_dining_intent = dietary_dining_intent and any(term in combined_text for term in NEARBY_LOCATION_TERMS)

    if nearby_dining_intent and "dining" not in filtered:
        filtered.append("dining")
    if nearby_dining_intent and "navigator" not in filtered:
        filtered.append("navigator")

    navigation_only_intent = any(
        token in combined_text
        for token in ["how do i get to", "get to", "directions", "where is", "navigate", "route", "library"]
    ) and not dining_place_intent
    quiet_study_intent = any(token in combined_text for token in ["quiet study", "study spot", "study spots"]) and not dining_place_intent

    if navigation_only_intent:
        filtered = [task for task in filtered if task != "dining"]
        if "navigator" not in filtered:
            filtered.append("navigator")

    if quiet_study_intent:
        filtered = [task for task in filtered if task != "dining"]
        if "study_resources" not in filtered:
            filtered.append("study_resources")

    return filtered


async def _enrich_message_with_gemini(user_message: str) -> str:
    """Use Gemini to rewrite user message descriptively."""
    prompt = MESSAGE_ENRICHMENT_PROMPT.format(user_message=user_message)
    fallback = _fallback_enrich_message(user_message)
    try:
        enriched = await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 4)
        return _normalize_enriched_message(enriched, fallback)
    except (GeminiClientError, Exception):
        return fallback


async def run(user_message: str) -> TaskPlannerResponse:
    """
    Task Planner: 
    1. Enriches user message with descriptive rewrite
    2. Routes to applicable agents
    3. Determines parallelization strategy
    4. Returns context for each agent
    """
    
    # Prefer retry-based async AI calls for both rewrite and routing to minimize fallback behavior.
    enriched_message = await _enrich_message_with_gemini(user_message)
    enrichment_used_ai = enriched_message != _fallback_enrich_message(user_message)
    prompt = TASK_PLANNER_PROMPT.format(enriched_message=enriched_message)

    try:
        raw = await call_gemini_with_retry(prompt, "gemini-3.1-flash-lite", 10)
        response = _parse_planner_json(raw)
        if not response.tasks and any(term in enriched_message.lower() for term in DIETARY_TERMS):
            recovery_prompt = (
                TASK_PLANNER_PROMPT.format(enriched_message=enriched_message)
                + "\nImportant: This request includes dietary constraints and is actionable. Select at least one agent if possible."
            )
            recovery_raw = await call_gemini_with_retry(recovery_prompt, "gemini-3.1-flash-lite", 10)
            recovery = _parse_planner_json(recovery_raw)
            if recovery.tasks:
                response = recovery
        response.tasks = _enforce_navigation_intent(response.tasks, user_message, enriched_message)
        response.tasks = _enforce_finance_intent(response.tasks, user_message, enriched_message)
        response.tasks = _enforce_precise_agent_activation(response.tasks, user_message, enriched_message)
        response.context.enriched_query = enriched_message  # type: ignore
        response.context.ai_enrichment_used = enrichment_used_ai  # type: ignore
        response.context.ai_routing_used = True  # type: ignore
        response.context.ai_error = None  # type: ignore
        return response
    except (GeminiClientError, json.JSONDecodeError, ValueError, KeyError, Exception) as exc:
        response = _fallback_plan(user_message, enriched_message)
        response.tasks = _enforce_navigation_intent(response.tasks, user_message, enriched_message)
        response.tasks = _enforce_finance_intent(response.tasks, user_message, enriched_message)
        response.tasks = _enforce_precise_agent_activation(response.tasks, user_message, enriched_message)
        response.context.enriched_query = enriched_message  # type: ignore
        response.context.ai_enrichment_used = enrichment_used_ai  # type: ignore
        response.context.ai_routing_used = False  # type: ignore
        response.context.ai_error = f"{type(exc).__name__}: {exc}"  # type: ignore
        return response
