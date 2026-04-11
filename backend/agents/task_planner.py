from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from backend.models.schemas import TaskPlannerContext, TaskPlannerResponse
from backend.utils.gemini_client import GeminiClientError, call_gemini

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
    
    return enhance


def _fallback_plan(user_message: str, enriched_message: str = "") -> TaskPlannerResponse:
    """Fallback task routing using keyword matching."""
    if not enriched_message:
        enriched_message = _fallback_enrich_message(user_message)
    
    text = user_message.lower()
    tasks: list[str] = []
    constraints: dict[str, Any] = {}

    # Keyword-based agent activation
    if any(k in text for k in ["exam", "deadline", "study", "assignment", "quiz", "class", "schedule"]):
        tasks.append("schedule")
    if any(k in text for k in ["eat", "dining", "food", "lunch", "dinner", "breakfast", "restaurant", "cafe"]):
        tasks.append("dining")
    if any(k in text for k in ["event", "club", "workshop", "seminar", "talk", "concert", "movie"]):
        tasks.append("events")
    if any(k in text for k in ["budget", "$", "spend", "finance", "money", "cost", "price"]):
        tasks.append("finance")
        budget_match = re.search(r"\$(\d+)", user_message)
        if budget_match:
            constraints["budget"] = int(budget_match.group(1))
    if any(k in text for k in ["where is", "navigate", "directions", "walk to", "map", "location", "building"]):
        tasks.append("navigator")
        location_match = re.search(r"near\s+(\w+)|\s+at\s+(\w+)|locate\s+(\w+)", user_message)
        if location_match:
            loc = location_match.group(1) or location_match.group(2) or location_match.group(3)
            constraints["location"] = loc
    if any(k in text for k in ["tutor", "office hours", "study resources", "help", "learn"]):
        tasks.append("study_resources")
    if any(k in text for k in ["job", "internship", "research", "lab", "resume", "career", "hiring"]):
        tasks.append("jobs_research")

    if not tasks:
        tasks = ["schedule"]  # Default to schedule

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
    data = json.loads(raw)
    tasks = data.get("tasks", [])
    priority = data.get("priority", "medium")
    
    context_data = data.get("context", {})
    context = TaskPlannerContext(
        budget=context_data.get("budget"),
        deadline_mentioned=context_data.get("deadline_mentioned", False),
        location_mentioned=context_data.get("location_mentioned"),
    )
    
    return TaskPlannerResponse(
        tasks=tasks,
        priority=priority,
        context=context,
    )


async def _enrich_message_with_gemini(user_message: str) -> str:
    """Use Gemini to rewrite user message descriptively."""
    prompt = MESSAGE_ENRICHMENT_PROMPT.format(user_message=user_message)
    try:
        enriched = await asyncio.to_thread(call_gemini, prompt, "gemini-3.1-flash-lite", 4)
        return enriched.strip() if enriched else _fallback_enrich_message(user_message)
    except (GeminiClientError, Exception):
        return _fallback_enrich_message(user_message)


async def run(user_message: str) -> TaskPlannerResponse:
    """
    Task Planner: 
    1. Enriches user message with descriptive rewrite
    2. Routes to applicable agents
    3. Determines parallelization strategy
    4. Returns context for each agent
    """
    
    # Step 1: Enrich the message
    enriched_message = await _enrich_message_with_gemini(user_message)
    
    # Step 2: Route to agents
    prompt = TASK_PLANNER_PROMPT.format(enriched_message=enriched_message)

    try:
        raw = await asyncio.to_thread(call_gemini, prompt, "gemini-3.1-flash-lite", 6)
        response = _parse_planner_json(raw)
        # Store enriched message in context for downstream use
        response.context.enriched_query = enriched_message  # type: ignore
        return response
    except (GeminiClientError, json.JSONDecodeError, ValueError, KeyError, Exception):
        # Fallback to keyword-based routing
        return _fallback_plan(user_message, enriched_message)
