from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

AgentFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
ProgressFn = Callable[[dict[str, Any]], Awaitable[None]]


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


async def _emit_progress(progress_callback: ProgressFn | None, event: dict[str, Any]) -> None:
    if progress_callback is None:
        return
    try:
        await progress_callback(event)
    except Exception:
        # Progress emission should never block agent execution.
        return


async def _run_with_timeout(
    agent_name: str,
    agent_fn: AgentFn,
    context: dict[str, Any],
    timeout_seconds: int,
    progress_callback: ProgressFn | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    workflow_steps: list[dict[str, Any]] = []
    await _emit_progress(
        progress_callback,
        {
            "type": "agent_status",
            "agent": agent_name,
            "status": "running",
        },
    )
    workflow_steps.append({"step": "initial_run", "status": "running"})

    try:
        result = await asyncio.wait_for(agent_fn(context), timeout=timeout_seconds)
        has_error = isinstance(result, dict) and bool(result.get("error"))

        if has_error:
            workflow_steps.append(
                {
                    "step": "initial_run",
                    "status": "error",
                    "detail": str(result.get("error")),
                }
            )
            await _emit_progress(
                progress_callback,
                {
                    "type": "agent_status",
                    "agent": agent_name,
                    "status": "retrying",
                    "reason": "initial_result_error",
                },
            )
            # Backoff delay to reduce transient API/rate-limit failures.
            await asyncio.sleep(0.8)
            retry_context = dict(context)
            retry_context["recovery_pass"] = True
            retry_context["prior_error"] = result.get("error")
            retry_result = await asyncio.wait_for(agent_fn(retry_context), timeout=timeout_seconds)
            retry_has_error = isinstance(retry_result, dict) and bool(retry_result.get("error"))
            if retry_has_error:
                workflow_steps.append(
                    {
                        "step": "recovery_run",
                        "status": "error",
                        "detail": str(retry_result.get("error")),
                    }
                )
            else:
                workflow_steps.append({"step": "recovery_run", "status": "ok"})
                result = retry_result
        else:
            workflow_steps.append({"step": "initial_run", "status": "ok"})

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        if isinstance(result, dict):
            result["workflow_steps"] = workflow_steps
        ai_output_preview = None
        if isinstance(result, dict):
            for key in (
                "ai_recommendation",
                "ai_summary",
                "ai_strategy",
                "ai_tip",
                "cold_email",
            ):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    ai_output_preview = value.strip()[:220]
                    break
        event = {
            "type": "agent_status",
            "agent": agent_name,
            "status": "completed",
            "elapsed_ms": elapsed_ms,
            "result_keys": sorted(list(result.keys())) if isinstance(result, dict) else [],
        }
        if ai_output_preview:
            event["ai_output_preview"] = ai_output_preview
        await _emit_progress(
            progress_callback,
            event,
        )
        return result
    except asyncio.TimeoutError:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        timeout_result = {
            "agent": agent_name,
            "error": "Agent timed out",
            "status": "timeout",
            "elapsed_ms": elapsed_ms,
        }
        await _emit_progress(
            progress_callback,
            {
                "type": "agent_status",
                "agent": agent_name,
                "status": "timeout",
                "elapsed_ms": elapsed_ms,
                "error": "Agent timed out",
            },
        )
        return timeout_result
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        error_detail = f"{type(exc).__name__}: {exc}"
        failed_result = {
            "agent": agent_name,
            "error": error_detail,
            "status": "failed",
            "elapsed_ms": elapsed_ms,
        }
        await _emit_progress(
            progress_callback,
            {
                "type": "agent_status",
                "agent": agent_name,
                "status": "failed",
                "elapsed_ms": elapsed_ms,
                "error": error_detail,
            },
        )
        return failed_result


async def run_agents(
    tasks: list[str],
    context: dict[str, Any],
    agent_map: dict[str, AgentFn] | None = None,
    timeout_seconds: int = 14,
    progress_callback: ProgressFn | None = None,
) -> dict[str, dict[str, Any]]:
    resolved_map = agent_map or _default_agent_map()
    selected = {name: fn for name, fn in resolved_map.items() if name in tasks}

    results = await asyncio.gather(
        *[
            _run_with_timeout(name, fn, context, timeout_seconds, progress_callback)
            for name, fn in selected.items()
        ],
        return_exceptions=False,
    )

    return dict(zip(selected.keys(), results))
