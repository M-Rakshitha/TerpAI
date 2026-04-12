from __future__ import annotations

import asyncio
import json

import pytest

from backend.agents import aggregator, router, task_planner
from backend import main as backend_main


@pytest.mark.asyncio
async def test_multi_agent_pipeline_planner_router_aggregator(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_call_gemini(prompt: str, model: str, timeout_seconds: int) -> str:
        if "Return ONLY this JSON format" in prompt:
            return (
                '{"tasks": ["dining", "navigator"], "priority": "high", '
                '"enriched_query": "Need vegan dinner under $15 and directions", '
                '"context": {"budget": 15, "deadline_mentioned": false, "location_mentioned": "AVW", "extracted_constraints": {}}, '
                '"parallel_groups": ["all"], "reasoning": "Needs food and directions"}'
            )
        return "Need vegan dinner under $15 and directions to AVW."

    monkeypatch.setattr(task_planner, "call_gemini", _fake_call_gemini)

    plan = await task_planner.run("Find vegan dinner under $15 and walk me to AVW")
    assert "dining" in plan.tasks
    assert "navigator" in plan.tasks
    assert plan.context.budget == 15

    async def _dining_agent(context: dict) -> dict:
        return {
            "agent": "dining",
            "options": [
                {
                    "name": "South Campus Dining",
                    "distance_min": 8,
                    "budget_ok": True,
                    "hours_open": True,
                    "dietary_tags": ["vegan"],
                }
            ],
        }

    async def _navigator_agent(context: dict) -> dict:
        return {
            "agent": "navigator",
            "origin": "McKeldin Library",
            "destination": "A.V. Williams Building",
            "walk_minutes": 10,
            "steps": ["Head toward AVW", "Arrive at AVW"],
            "map_url": "https://map.umd.edu/?start=McKeldin&stop=AVW",
        }

    context = {
        "user_message": "Find vegan dinner under $15 and walk me to AVW",
        "budget": plan.context.budget,
        "origin": "McKeldin Library",
        "destination": "A.V. Williams Building",
    }
    agent_map = {
        "dining": _dining_agent,
        "navigator": _navigator_agent,
    }

    results = await router.run_agents(plan.tasks, context, agent_map=agent_map, timeout_seconds=2)
    response = aggregator.aggregate(
        context["user_message"],
        plan.tasks,
        results,
        execution_trace=[{"type": "planner_status", "status": "completed"}],
    )

    assert response.results.dining is not None
    assert response.results.navigator is not None
    assert response.results.dining.options[0].budget_ok is True
    assert response.results.navigator.destination == "A.V. Williams Building"
    assert response.presentation is not None
    assert response.presentation.get("layout") == "dashboard"
    assert isinstance(response.presentation.get("sections"), list)
    assert isinstance(response.presentation.get("visual_report"), dict)
    assert response.agent_execution is not None
    assert response.agent_outputs is not None


@pytest.mark.asyncio
async def test_router_parallel_multi_agent_failures_and_timeouts() -> None:
    async def _slow_agent(context: dict) -> dict:
        await asyncio.sleep(0.05)
        return {"agent": "dining"}

    async def _failing_agent(context: dict) -> dict:
        raise RuntimeError("agent failure")

    results = await router.run_agents(
        ["dining", "navigator"],
        {"user_message": "test"},
        agent_map={"dining": _slow_agent, "navigator": _failing_agent},
        timeout_seconds=0.01,
    )

    assert set(results.keys()) == {"dining", "navigator"}
    assert isinstance(results["dining"], dict)
    assert results["dining"].get("status") == "timeout"
    assert isinstance(results["navigator"], dict)
    assert results["navigator"].get("status") in {"timeout", "failed"}


@pytest.mark.asyncio
async def test_aggregator_keeps_known_agent_results_only() -> None:
    combined = aggregator.aggregate(
        "Need food and directions",
        ["dining", "navigator"],
        {
            "dining": {
                "agent": "dining",
                "options": [
                    {
                        "name": "251 North Dining",
                        "distance_min": 7,
                        "budget_ok": True,
                        "hours_open": True,
                        "dietary_tags": ["vegetarian"],
                    }
                ],
            },
            "unknown_agent": {"agent": "unknown"},
        },
    )

    assert combined.results.dining is not None
    assert combined.results.dining.options[0].name == "251 North Dining"
    assert combined.results.navigator is None
    assert combined.presentation is not None
    assert combined.presentation.get("summary", {}).get("title") == "TerpAI Results"


@pytest.mark.asyncio
async def test_aggregator_normalizes_events_options_to_schema_events() -> None:
    combined = aggregator.aggregate(
        "Show me events",
        ["events"],
        {
            "events": {
                "agent": "events",
                "options": [
                    {
                        "name": "Campus Movie Night",
                        "date": "2026-04-11",
                        "time": "8:00 PM",
                        "location": "STAMP",
                        "free_food": True,
                        "tags": ["movie", "social"],
                    }
                ],
            }
        },
    )

    assert combined.results.events is not None
    assert combined.results.events.events[0].title == "Campus Movie Night"
    assert combined.results.events.events[0].location == "STAMP"
    assert combined.presentation is not None
    sections = combined.presentation.get("sections", [])
    assert any(section.get("id") == "events" for section in sections)


@pytest.mark.asyncio
async def test_aggregator_includes_agent_activation_status_section() -> None:
    combined = aggregator.aggregate(
        "Find vegan dinner and route me there",
        ["dining", "navigator"],
        {
            "dining": {
                "agent": "dining",
                "options": [],
                "data_sources": {"gemini_used": False},
                "error": "No live dining results",
            },
            "navigator": {
                "agent": "navigator",
                "origin": "A",
                "destination": "B",
                "walk_minutes": 5,
                "steps": ["Walk"],
                "map_url": "https://map.umd.edu",
                "data_sources": {"gemini_used": True},
            },
        },
    )

    assert combined.presentation is not None
    sections = combined.presentation.get("sections", [])
    activation = next((section for section in sections if section.get("id") == "agent_activation"), None)
    assert activation is not None
    items = activation.get("items", [])
    assert any(item.get("agent") == "dining" and item.get("status") == "error" for item in items)
    assert any(item.get("agent") == "navigator" and item.get("gemini_used") is True for item in items)


@pytest.mark.asyncio
async def test_persist_latest_response_snapshot(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = aggregator.aggregate(
        "Need dinner under $15",
        ["dining"],
        {
            "dining": {
                "agent": "dining",
                "options": [
                    {
                        "name": "South Campus Dining",
                        "distance_min": 8,
                        "budget_ok": True,
                        "hours_open": True,
                        "dietary_tags": ["vegan"],
                    }
                ],
            }
        },
    )

    snapshot_path = tmp_path / "latest_query_response.json"
    monkeypatch.setattr(backend_main, "RAW_RESPONSE_PATH", snapshot_path)

    await backend_main._persist_latest_response(response)

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["query"] == "Need dinner under $15"
    assert payload["presentation"]["visual_report"]["headline"]
