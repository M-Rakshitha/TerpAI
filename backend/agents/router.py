from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

AgentFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _default_agent_map() -> dict[str, AgentFn]:
    from backend.agents import (
        dining_agent,
        events_agent,
        finance_agent,
        jobs_research_agent,
        navigator_agent,
        schedule_agent,
        study_resources_agent,
    )

    return {
        "schedule": schedule_agent.run,
        "dining": dining_agent.run,
        "events": events_agent.run,
        "finance": finance_agent.run,
        "navigator": navigator_agent.run,
        "study_resources": study_resources_agent.run,
        "jobs_research": jobs_research_agent.run,
    }


async def _run_with_timeout(agent_fn: AgentFn, context: dict[str, Any], timeout_seconds: int) -> dict[str, Any] | None:
    try:
        return await asyncio.wait_for(agent_fn(context), timeout=timeout_seconds)
    except Exception:
        return None


async def run_agents(
    tasks: list[str],
    context: dict[str, Any],
    agent_map: dict[str, AgentFn] | None = None,
    timeout_seconds: int = 8,
) -> dict[str, dict[str, Any] | None]:
    resolved_map = agent_map or _default_agent_map()
    selected = {name: fn for name, fn in resolved_map.items() if name in tasks}

    results = await asyncio.gather(
        *[_run_with_timeout(fn, context, timeout_seconds) for fn in selected.values()],
        return_exceptions=False,
    )

    return dict(zip(selected.keys(), results))
