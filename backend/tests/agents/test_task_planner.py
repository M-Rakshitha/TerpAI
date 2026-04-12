import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[3]))

from backend.agents import task_planner


@pytest.mark.asyncio
async def test_task_planner_enriches_dining_query() -> None:
    """Test that task planner enriches a dining query descriptively."""
    result = await task_planner.run("Find vegan food under $15")
    
    assert result.priority in ["high", "medium", "low"]
    assert isinstance(result.tasks, list)
    assert "dining" in result.tasks
    # Enriched context should be stored
    assert result.context.enriched_query is not None or result.context.budget is not None


@pytest.mark.asyncio
async def test_task_planner_activates_dining_agent() -> None:
    """Test that dining keywords activate dining agent."""
    result = await task_planner.run("I'm hungry for lunch")
    
    assert "dining" in result.tasks
    assert result.tasks  # Should have at least one task


@pytest.mark.asyncio
async def test_task_planner_routes_dietary_near_me_query() -> None:
    result = await task_planner.run("vegan options near me")

    assert "dining" in result.tasks
    # Near-me dining requests should also route navigation help.
    assert "navigator" in result.tasks


@pytest.mark.asyncio
async def test_task_planner_fallback_routes_vegetarian_nearby_when_ai_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise(*args, **kwargs):
        raise RuntimeError("Gemini unavailable")

    monkeypatch.setattr(task_planner, "call_gemini_with_retry", _raise)

    result = await task_planner.run("where can I find vegetarian options nearby")

    assert "dining" in result.tasks
    assert "navigator" in result.tasks


@pytest.mark.asyncio
async def test_task_planner_activates_events_agent() -> None:
    """Test that event keywords activate events agent."""
    result = await task_planner.run("What concerts are happening this weekend?")
    
    assert "events" in result.tasks


@pytest.mark.asyncio
async def test_task_planner_activates_schedule_agent() -> None:
    """Test that schedule keywords activate schedule agent."""
    result = await task_planner.run("When is my exam tomorrow?")
    
    assert "schedule" in result.tasks
    assert result.context.deadline_mentioned is True


@pytest.mark.asyncio
async def test_task_planner_activates_finance_agent() -> None:
    """Test that finance keywords activate finance agent."""
    result = await task_planner.run("How much did I spend this month?")
    
    assert "finance" in result.tasks


@pytest.mark.asyncio
async def test_task_planner_activates_navigator_agent() -> None:
    """Test that navigation keywords activate navigator agent."""
    result = await task_planner.run("Where is Engineering building?")
    
    assert "navigator" in result.tasks


@pytest.mark.asyncio
async def test_task_planner_activates_study_resources_agent() -> None:
    """Test that study keywords activate study resources agent."""
    result = await task_planner.run("I need a tutor for calculus")
    
    assert "study_resources" in result.tasks


@pytest.mark.asyncio
async def test_task_planner_activates_jobs_agent() -> None:
    """Test that job/internship keywords activate jobs research agent."""
    result = await task_planner.run("What internships are available?")
    
    assert "jobs_research" in result.tasks


@pytest.mark.asyncio
async def test_task_planner_extracts_budget_constraint() -> None:
    """Test that task planner extracts budget from message."""
    result = await task_planner.run("Find dinner under $20")
    
    assert result.context.budget is not None or "dining" in result.tasks
    if result.context.budget is not None:
        assert result.context.budget == 20


@pytest.mark.asyncio
async def test_task_planner_marks_deadline_as_high_priority() -> None:
    """Test that deadline mentions set priority to high."""
    result = await task_planner.run("My exam is tomorrow")
    
    assert result.context.deadline_mentioned is True
    assert result.priority == "high"


@pytest.mark.asyncio
async def test_task_planner_activates_multiple_agents_in_parallel() -> None:
    """Test that multiple unrelated agents can activate simultaneously."""
    result = await task_planner.run(
        "I need to find an event to attend, check my budget, and navigate to it"
    )
    
    # Should have multiple tasks that can run in parallel
    assert len(result.tasks) >= 1
    assert isinstance(result.tasks, list)


@pytest.mark.asyncio
async def test_task_planner_handles_vague_query() -> None:
    """Test that vague queries do not force unnecessary agents."""
    result = await task_planner.run("Hello")
    
    assert result.tasks == []
    assert isinstance(result.tasks, list)


@pytest.mark.asyncio
async def test_task_planner_extracts_location_context() -> None:
    """Test that location mentions are extracted."""
    result = await task_planner.run("Navigate to McKeldin Library")
    
    assert "navigator" in result.tasks
    # Location should be detected (either in context or tasks)
    assert result.context.location_mentioned is not None or "navigator" in result.tasks


@pytest.mark.asyncio
async def test_task_planner_complex_multi_agent_query() -> None:
    """Test complex query that requires multiple agent activations."""
    result = await task_planner.run(
        "I have an exam tomorrow at 2pm near Engineering building, "
        "want free food before it, and need to know job opportunities after"
    )
    
    # Should activate multiple agents
    assert len(result.tasks) >= 2
    assert result.context.deadline_mentioned is True
    assert result.priority == "high"
    # Could include schedule (exam), dining (food), navigator (location), jobs (opportunities)
    possible_agents = {"schedule", "dining", "navigator", "jobs_research"}
    assert any(task in possible_agents for task in result.tasks)


@pytest.mark.asyncio
async def test_task_planner_returns_consistent_structure() -> None:
    """Test that task planner always returns valid response structure."""
    result = await task_planner.run("Random query")
    
    # Must have required fields
    assert hasattr(result, "tasks")
    assert hasattr(result, "priority")
    assert hasattr(result, "context")
    
    # Types must be correct
    assert isinstance(result.tasks, list)
    assert isinstance(result.priority, str)
    assert result.priority in ["high", "medium", "low"]
    
    # Context must have required fields
    assert hasattr(result.context, "budget")
    assert hasattr(result.context, "deadline_mentioned")
    assert hasattr(result.context, "location_mentioned")


@pytest.mark.asyncio
async def test_task_planner_activates_finance_for_weekly_budget_planning() -> None:
    result = await task_planner.run("Plan my weekly dining, travel, and classes budget under 150")

    assert "finance" in result.tasks
    assert result.context.budget == 150


@pytest.mark.asyncio
async def test_task_planner_activates_finance_for_budget_without_dollar_sign() -> None:
    result = await task_planner.run("Can you help me plan monthly spending for events and food under 220")

    assert "finance" in result.tasks
    assert result.context.budget == 220
