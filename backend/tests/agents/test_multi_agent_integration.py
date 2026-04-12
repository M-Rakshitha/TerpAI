from __future__ import annotations

import asyncio
import json

import pytest

from backend.agents import aggregator, router, task_planner
from backend import main as backend_main


@pytest.mark.asyncio
async def test_multi_agent_pipeline_planner_router_aggregator(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_gemini_with_retry(prompt: str, model: str, timeout_seconds: int, *args, **kwargs) -> str:
        if "Return ONLY this JSON format" in prompt:
            return (
                '{"tasks": ["dining", "navigator"], "priority": "high", '
                '"enriched_query": "Need vegan dinner under $15 and directions", '
                '"context": {"budget": 15, "deadline_mentioned": false, "location_mentioned": "AVW", "extracted_constraints": {}}, '
                '"parallel_groups": ["all"], "reasoning": "Needs food and directions"}'
            )
        return "Need vegan dinner under $15 and directions to AVW."

    monkeypatch.setattr(task_planner, "call_gemini_with_retry", _fake_call_gemini_with_retry)

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


@pytest.mark.asyncio
async def test_persist_latest_events_trace_overwrites_with_last_request(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    trace_path = tmp_path / "events.jsonl"
    monkeypatch.setattr(backend_main, "EVENTS_TRACE_PATH", trace_path)

    response_one = aggregator.aggregate("first request", ["dining"], {"dining": {"agent": "dining", "options": []}})
    response_two = aggregator.aggregate("second request", ["events"], {"events": {"agent": "events", "options": []}})

    await backend_main._persist_latest_events_trace(
        message="first request",
        request_id="req-1",
        trace=[{"type": "planner_status", "status": "completed", "request_id": "req-1"}],
        response=response_one,
    )
    await backend_main._persist_latest_events_trace(
        message="second request",
        request_id="req-2",
        trace=[{"type": "planner_status", "status": "completed", "request_id": "req-2"}],
        response=response_two,
    )

    content = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 1
    payload = json.loads(content[0])
    assert payload["request_id"] == "req-2"
    assert payload["message"] == "second request"
    assert payload["response"]["query"] == "second request"


@pytest.mark.asyncio
async def test_router_activates_two_agents_in_parallel_and_aggregates() -> None:
    async def _dining_agent(context: dict) -> dict:
        await asyncio.sleep(0.01)
        return {
            "agent": "dining",
            "options": [
                {
                    "name": "Yahentamitsi Dining Hall",
                    "distance_min": 7,
                    "budget_ok": True,
                    "hours_open": True,
                    "dietary_tags": ["vegan"],
                }
            ],
        }

    async def _events_agent(context: dict) -> dict:
        await asyncio.sleep(0.01)
        return {
            "agent": "events",
            "options": [
                {
                    "name": "Career Fair",
                    "date": "2026-04-12",
                    "time": "2:00 PM",
                    "location": "STAMP",
                    "tags": ["career"],
                    "free_food": False,
                }
            ],
        }

    tasks = ["dining", "events"]
    context = {"user_message": "Find dinner and events"}
    results = await router.run_agents(
        tasks,
        context,
        agent_map={"dining": _dining_agent, "events": _events_agent},
        timeout_seconds=2,
    )

    combined = aggregator.aggregate(context["user_message"], tasks, results)
    assert combined.results.dining is not None
    assert combined.results.events is not None
    assert combined.results.dining.options[0].name == "Yahentamitsi Dining Hall"
    assert combined.results.events.events[0].title == "Career Fair"


@pytest.mark.asyncio
async def test_router_activates_three_agents_with_one_error_and_keeps_others() -> None:
    async def _dining_agent(context: dict) -> dict:
        return {
            "agent": "dining",
            "options": [
                {
                    "name": "South Campus Dining",
                    "distance_min": 6,
                    "budget_ok": True,
                    "hours_open": True,
                    "dietary_tags": ["vegetarian"],
                }
            ],
        }

    async def _navigator_agent(context: dict) -> dict:
        return {
            "agent": "navigator",
            "origin": "Reckord Armory",
            "destination": "ESJ",
            "walk_minutes": 9,
            "steps": ["Walk north", "Arrive at ESJ"],
            "map_url": "https://map.umd.edu/?start=Reckord&stop=ESJ",
        }

    async def _finance_agent(context: dict) -> dict:
        return {
            "agent": "finance",
            "error": "Insufficient live pricing evidence was found for requested categories.",
            "status": "failed",
        }

    tasks = ["dining", "navigator", "finance"]
    results = await router.run_agents(
        tasks,
        {"user_message": "Food + route + budget check"},
        agent_map={
            "dining": _dining_agent,
            "navigator": _navigator_agent,
            "finance": _finance_agent,
        },
        timeout_seconds=2,
    )

    combined = aggregator.aggregate("Food + route + budget check", tasks, results)
    assert combined.results.dining is not None
    assert combined.results.navigator is not None
    assert combined.results.finance is None

    sections = combined.presentation.get("sections", []) if combined.presentation else []
    activation = next((section for section in sections if section.get("id") == "agent_activation"), None)
    assert activation is not None
    items = activation.get("items", [])
    assert any(item.get("agent") == "dining" and item.get("status") == "ok" for item in items)
    assert any(item.get("agent") == "navigator" and item.get("status") == "ok" for item in items)
    assert any(item.get("agent") == "finance" and item.get("status") == "error" for item in items)


@pytest.mark.asyncio
async def test_router_parallel_agents_use_context_by_agent_scoping() -> None:
    async def _echo_agent(context: dict) -> dict:
        return {
            "agent": context["agent_name"],
            "received_prompt": context.get("agent_prompt"),
            "received_subtasks": context.get("agent_subtasks", []),
        }

    tasks = ["dining", "events"]
    context_by_agent = {
        "dining": {
            "agent_name": "dining",
            "agent_prompt": "Find cheap vegan dinner near AVW",
            "agent_subtasks": ["find options", "rank by budget"],
        },
        "events": {
            "agent_name": "events",
            "agent_prompt": "Find tech talks tomorrow",
            "agent_subtasks": ["collect events", "sort by relevance"],
        },
    }

    results = await router.run_agents(
        tasks,
        {"user_message": "multi"},
        context_by_agent=context_by_agent,
        agent_map={"dining": _echo_agent, "events": _echo_agent},
        timeout_seconds=2,
    )

    assert results["dining"]["received_prompt"] == "Find cheap vegan dinner near AVW"
    assert results["events"]["received_prompt"] == "Find tech talks tomorrow"
    assert results["dining"]["received_subtasks"] == ["find options", "rank by budget"]
    assert results["events"]["received_subtasks"] == ["collect events", "sort by relevance"]


@pytest.mark.asyncio
async def test_planner_drives_three_agent_activation_then_router_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_gemini_with_retry(prompt: str, model: str, timeout_seconds: int, *args, **kwargs) -> str:
        if "Return ONLY this JSON format" in prompt:
            return (
                '{"tasks": ["dining", "events", "navigator"], "priority": "medium", '
                '"enriched_query": "Dinner, event, and walking directions", '
                '"context": {"budget": 20, "deadline_mentioned": false, "location_mentioned": "Reckord Armory", "extracted_constraints": {}}, '
                '"parallel_groups": ["all"], "reasoning": "Need 3 agents for meal, event, and route"}'
            )
        return "Dinner, event, and walking directions"

    monkeypatch.setattr(task_planner, "call_gemini_with_retry", _fake_call_gemini_with_retry)

    plan = await task_planner.run("Find dinner, one event, and directions to ESJ from Reckord Armory")
    assert set(["dining", "events", "navigator"]).issubset(set(plan.tasks))

    async def _dining(context: dict) -> dict:
        return {"agent": "dining", "options": []}

    async def _events(context: dict) -> dict:
        return {"agent": "events", "options": []}

    async def _navigator(context: dict) -> dict:
        return {
            "agent": "navigator",
            "origin": "Reckord Armory",
            "destination": "ESJ",
            "walk_minutes": 9,
            "steps": ["Walk north"],
            "map_url": "https://map.umd.edu/?start=Reckord&stop=ESJ",
        }

    results = await router.run_agents(
        [agent for agent in plan.tasks if agent in {"dining", "events", "navigator"}],
        {"user_message": "Find dinner, one event, and directions"},
        agent_map={"dining": _dining, "events": _events, "navigator": _navigator},
        timeout_seconds=2,
    )

    assert set(results.keys()) == {"dining", "events", "navigator"}


@pytest.mark.asyncio
async def test_execute_pipeline_continues_with_fallback_when_location_required_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_persist(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(backend_main, "_persist_latest_response", _noop_persist)
    monkeypatch.setattr(backend_main, "_persist_latest_events_trace", _noop_persist)

    response, trace = await backend_main._execute_pipeline(
        message="give vegan options near me",
        request_id="req-loc-missing",
        include_context=False,
        client_context={},
        emit=None,
    )

    payload = response.model_dump(mode="json")
    assert payload.get("awaiting_user_input") in (False, None)
    assert payload.get("pipeline_paused") in (False, None)
    assert payload.get("location_fallback_used") is True
    assert "dining" in response.agents_used and "navigator" in response.agents_used
    assert any(event.get("type") == "user_input_request" and event.get("status") == "fallback_applied" for event in trace)


@pytest.mark.asyncio
async def test_execute_pipeline_continues_when_location_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_persist(*args, **kwargs) -> None:
        return None

    async def _fake_run_task_planner(_message: str):
        return backend_main.TaskPlannerResponse(
            tasks=["dining", "navigator"],
            priority="medium",
            context=backend_main.TaskPlannerContext(
                budget=None,
                deadline_mentioned=False,
                location_mentioned=None,
                enriched_query="give vegan options near me",
            ),
        )

    async def _fake_run_agents(tasks, context, **kwargs):
        assert "user_location" in context
        return {
            "dining": {
                "agent": "dining",
                "options": [
                    {
                        "name": "NuVegan Cafe",
                        "distance_min": 8,
                        "budget_ok": True,
                        "hours_open": True,
                        "dietary_tags": ["vegan"],
                    }
                ],
            },
            "navigator": {
                "agent": "navigator",
                "origin": "University of Maryland, College Park",
                "destination": "NuVegan Cafe",
                "walk_minutes": 12,
                "steps": ["Walk to destination"],
                "map_url": "https://www.google.com/maps/dir/?api=1&destination=NuVegan+Cafe",
            },
        }

    monkeypatch.setattr(backend_main, "_persist_latest_response", _noop_persist)
    monkeypatch.setattr(backend_main, "_persist_latest_events_trace", _noop_persist)
    monkeypatch.setattr(backend_main, "run_task_planner", _fake_run_task_planner)
    monkeypatch.setattr(backend_main, "run_agents", _fake_run_agents)

    response, trace = await backend_main._execute_pipeline(
        message="give vegan options near me",
        request_id="req-loc-denied",
        include_context=False,
        client_context={"location_permission_granted": False},
        emit=None,
    )

    payload = response.model_dump(mode="json")
    assert payload.get("awaiting_user_input") is False
    assert payload.get("pipeline_paused") is False
    assert "dining" in response.agents_used and "navigator" in response.agents_used
    assert payload.get("location_fallback_used") is True
    assert any(event.get("type") == "user_input_request" and event.get("status") == "fallback_applied" for event in trace)


@pytest.mark.asyncio
async def test_execute_pipeline_continues_when_location_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_persist(*args, **kwargs) -> None:
        return None

    async def _fake_run_task_planner(_message: str):
        return backend_main.TaskPlannerResponse(
            tasks=["dining", "navigator"],
            priority="medium",
            context=backend_main.TaskPlannerContext(
                budget=None,
                deadline_mentioned=False,
                location_mentioned="user_provided",
                enriched_query="give vegan options near me",
            ),
        )

    async def _fake_run_agents(tasks, context, **kwargs):
        assert context.get("user_location") == "38.9869,-76.9426"
        assert context.get("current_location_coords") == {"latitude": 38.9869, "longitude": -76.9426}
        return {
            "dining": {
                "agent": "dining",
                "options": [
                    {
                        "name": "NuVegan Cafe",
                        "distance_min": 8,
                        "budget_ok": True,
                        "hours_open": True,
                        "dietary_tags": ["vegan"],
                    }
                ],
            },
            "navigator": {
                "agent": "navigator",
                "origin": "38.9869,-76.9426",
                "destination": "NuVegan Cafe",
                "walk_minutes": 12,
                "steps": ["Walk to destination"],
                "map_url": "https://www.google.com/maps/dir/?api=1&destination=NuVegan+Cafe",
            },
        }

    monkeypatch.setattr(backend_main, "_persist_latest_response", _noop_persist)
    monkeypatch.setattr(backend_main, "_persist_latest_events_trace", _noop_persist)
    monkeypatch.setattr(backend_main, "run_task_planner", _fake_run_task_planner)
    monkeypatch.setattr(backend_main, "run_agents", _fake_run_agents)

    response, trace = await backend_main._execute_pipeline(
        message="give vegan options near me",
        request_id="req-loc-granted",
        include_context=False,
        client_context={
            "user_location": "38.9869,-76.9426",
            "current_location_coords": {"latitude": 38.9869, "longitude": -76.9426},
            "location_permission_granted": True,
        },
        emit=None,
    )

    payload = response.model_dump(mode="json")
    assert payload.get("awaiting_user_input") in (False, None)
    assert payload.get("pipeline_paused") in (False, None)
    assert "dining" in response.agents_used and "navigator" in response.agents_used
    assert any(event.get("type") == "user_input_request" and event.get("status") == "provided" for event in trace)


@pytest.mark.asyncio
async def test_recover_weak_results_builds_route_matrix_from_dining_options(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_run_agents(tasks, context, **kwargs):
        if tasks != ["navigator"]:
            return {}
        destination = str(context.get("destination") or "")
        return {
            "navigator": {
                "agent": "navigator",
                "origin": str(context.get("user_location") or "University of Maryland, College Park"),
                "destination": destination,
                "walk_minutes": 10,
                "steps": [f"Walk to {destination}"],
                "map_url": f"https://www.google.com/maps/dir/?api=1&destination={destination.replace(' ', '+')}",
            }
        }

    monkeypatch.setattr(backend_main, "run_agents", _fake_run_agents)

    results = {
        "dining": {
            "agent": "dining",
            "options": [
                {"name": "NuVegan Cafe", "distance_min": 8, "dietary_tags": ["vegan"]},
                {"name": "PLNT Burger (College Park)", "distance_min": 11, "dietary_tags": ["vegan"]},
            ],
        },
        "navigator": {
            "agent": "navigator",
            "origin": "University of Maryland, College Park",
            "destination": "vegan restaurants",
            "walk_minutes": 0,
            "steps": ["Open Google Maps and search for vegan restaurants."],
            "map_url": "https://www.google.com/maps/search/?api=1&query=vegan+restaurants",
        },
    }

    recovered = await backend_main._recover_weak_results(
        plan_tasks=["dining", "navigator"],
        base_context={
            "user_message": "vegan options near me",
            "enriched_query": "vegan options near me",
            "user_location": "University of Maryland, College Park",
        },
        per_agent_context={},
        results=results,
        progress_callback=None,
        timeout_seconds=40,
        best_output_pass=True,
    )

    navigator_payload = recovered.get("navigator") if isinstance(recovered.get("navigator"), dict) else {}
    route_matrix = navigator_payload.get("routes_by_option") if isinstance(navigator_payload.get("routes_by_option"), list) else []

    assert len(route_matrix) >= 2
    assert all(route.get("map_url") for route in route_matrix if isinstance(route, dict))
    assert all(route.get("description") for route in route_matrix if isinstance(route, dict))

    dining_payload = recovered.get("dining") if isinstance(recovered.get("dining"), dict) else {}
    dining_options = dining_payload.get("options") if isinstance(dining_payload.get("options"), list) else []
    assert all(option.get("route_map_url") for option in dining_options if isinstance(option, dict))
    assert all(option.get("route_description") for option in dining_options if isinstance(option, dict))


@pytest.mark.asyncio
async def test_recover_weak_results_reruns_generic_navigator_with_event_location(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_run_agents(tasks, context, **kwargs):
        if tasks != ["navigator"]:
            return {}
        destination = str(context.get("destination") or "")
        return {
            "navigator": {
                "agent": "navigator",
                "origin": "University of Maryland, College Park",
                "destination": destination,
                "walk_minutes": 9,
                "steps": [f"Walk to {destination}"],
                "map_url": f"https://www.google.com/maps/dir/?api=1&destination={destination.replace(' ', '+')}",
            }
        }

    monkeypatch.setattr(backend_main, "run_agents", _fake_run_agents)

    results = {
        "events": {
            "agent": "events",
            "events": [
                {"title": "Hack Night", "location": "STAMP Student Union", "start": "Fri 7 PM", "free_food": False, "tags": ["tech"]}
            ],
        },
        "navigator": {
            "agent": "navigator",
            "origin": "University of Maryland, College Park",
            "destination": "your objective",
            "walk_minutes": 0,
            "steps": ["Open Google Maps and search for your objective."],
            "map_url": "https://www.google.com/maps/search/?api=1&query=your+objective",
        },
    }

    recovered = await backend_main._recover_weak_results(
        plan_tasks=["events", "navigator"],
        base_context={
            "user_message": "what are some events this weekend",
            "enriched_query": "what are some events this weekend",
            "user_location": "University of Maryland, College Park",
        },
        per_agent_context={},
        results=results,
        progress_callback=None,
        timeout_seconds=40,
        best_output_pass=False,
    )

    navigator_payload = recovered.get("navigator") if isinstance(recovered.get("navigator"), dict) else {}
    assert navigator_payload.get("destination") == "STAMP Student Union"
    assert "destination=STAMP+Student+Union" in str(navigator_payload.get("map_url", ""))


def test_verify_agent_payload_marks_generic_navigator_for_reinvoke() -> None:
    verdict = backend_main._verify_agent_payload(
        "navigator",
        {
            "agent": "navigator",
            "origin": "University of Maryland, College Park",
            "destination": "your objective",
            "walk_minutes": 0,
            "steps": ["Open Google Maps and search for your objective."],
            "map_url": "https://www.google.com/maps/search/?api=1&query=your+objective",
        },
    )

    assert verdict.get("should_reinvoke") is True
    assert "generic_navigation" in (verdict.get("gaps") or [])


def test_fallback_plan_fast_includes_dining_for_dumplings_near_me() -> None:
    plan = backend_main._fallback_plan_fast("dumplings near me")

    assert "dining" in plan.tasks
    assert "navigator" in plan.tasks
    assert plan.context.ai_error == "planner_timeout_fallback"
