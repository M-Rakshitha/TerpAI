from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

AgentFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
ProgressFn = Callable[[dict[str, Any]], Awaitable[None]]

DEFAULT_SUBTASKS = [
    "Gather required inputs",
    "Run agent analysis",
    "Finalize structured response",
]

AGENT_COMPLETION_MESSAGES = {
    "schedule": "Schedule planning complete: deadlines, study blocks, and priorities are ready.",
    "dining": "Dining analysis complete: options were ranked with budget and location checks.",
    "events": "Event discovery complete: relevant events were collected and prioritized.",
    "finance": "Budget analysis complete: spending guidance and feasibility checks are ready.",
    "navigator": "Navigation complete: route guidance and map-ready directions are available.",
    "study_resources": "Study resources complete: tutoring and academic support options are organized.",
    "jobs_research": "Career research complete: opportunities and actionable next steps are ready.",
}


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


def _coerce_subtasks(context: dict[str, Any]) -> list[str]:
    raw = context.get("agent_subtasks")
    if isinstance(raw, list):
        subtasks = [str(item).strip() for item in raw if str(item).strip()]
        if subtasks:
            return subtasks
    return list(DEFAULT_SUBTASKS)


def _build_step_results(
    agent_name: str,
    subtasks: list[str],
    final_status: str,
    result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    completion_message = AGENT_COMPLETION_MESSAGES.get(agent_name, "Agent workflow complete with usable results.")
    result_keys = sorted(list(result.keys())) if isinstance(result, dict) else []
    evidence = result_keys[:6]

    step_results: list[dict[str, Any]] = []
    for index, subtask in enumerate(subtasks):
        if final_status == "completed":
            status = "completed"
            message = f"Step {index + 1} complete: {subtask}."
            if index == len(subtasks) - 1:
                message = completion_message
        elif final_status in {"failed", "timeout"}:
            status = "failed" if index == 0 else "skipped"
            message = f"Step {index + 1} could not complete due to {final_status}." if index == 0 else "Skipped due to earlier failure."
        else:
            status = "queued"
            message = "Waiting for execution."

        step_results.append(
            {
                "step": f"step_{index + 1}",
                "subtask": subtask,
                "status": status,
                "message": message,
                "evidence_keys": evidence,
            }
        )

    return step_results


async def _run_with_timeout(
    agent_name: str,
    agent_fn: AgentFn,
    context: dict[str, Any],
    timeout_seconds: int,
    progress_callback: ProgressFn | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    workflow_steps: list[dict[str, Any]] = []
    subtasks = _coerce_subtasks(context)
    total_steps = len(subtasks)
    current_step = 1

    async def _emit_step_event(step_index: int, status: str, message: str) -> None:
        subtask = subtasks[max(0, min(step_index - 1, total_steps - 1))] if subtasks else ""
        await _emit_progress(
            progress_callback,
            {
                "type": "agent_step",
                "agent": agent_name,
                "step_index": step_index,
                "total_steps": total_steps,
                "subtask": subtask,
                "status": status,
                "message": message,
            },
        )

    async def _running_heartbeat() -> None:
        nonlocal current_step
        tick = 0
        while True:
            await asyncio.sleep(2.0)
            tick += 1
            if total_steps > 1 and tick % 2 == 0:
                next_step = min(total_steps, current_step + 1)
                if next_step != current_step:
                    current_step = next_step
                    await _emit_step_event(
                        current_step,
                        "running",
                        f"Working on step {current_step} of {total_steps}: {subtasks[current_step - 1]}",
                    )
            await _emit_progress(
                progress_callback,
                {
                    "type": "agent_status",
                    "agent": agent_name,
                    "status": "running",
                    "detail": f"Working on step {current_step}/{total_steps}: {subtasks[current_step - 1]}",
                    "current_step": current_step,
                    "total_steps": total_steps,
                },
            )

    await _emit_progress(
        progress_callback,
        {
            "type": "agent_status",
            "agent": agent_name,
            "status": "running",
            "current_step": 1,
            "total_steps": total_steps,
            "detail": f"Starting step 1/{total_steps}: {subtasks[0] if subtasks else 'Initialize agent workflow'}",
        },
    )
    await _emit_step_event(
        1,
        "running",
        f"Starting step 1 of {total_steps}: {subtasks[0] if subtasks else 'Initialize agent workflow'}",
    )
    workflow_steps.append({"step": "initial_run", "status": "running"})
    heartbeat_task = asyncio.create_task(_running_heartbeat())

    try:
        result = await asyncio.wait_for(agent_fn(context), timeout=timeout_seconds)
        has_error = isinstance(result, dict) and bool(result.get("error"))
        final_status = "completed"

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
                    "current_step": 1,
                    "total_steps": total_steps,
                },
            )
            await _emit_step_event(1, "running", "Retrying agent workflow after initial error.")
            # Backoff delay to reduce transient API/rate-limit failures.
            await asyncio.sleep(0.8)
            retry_context = dict(context)
            retry_context["recovery_pass"] = True
            retry_context["prior_error"] = result.get("error")
            retry_result = await asyncio.wait_for(agent_fn(retry_context), timeout=timeout_seconds)
            retry_has_error = isinstance(retry_result, dict) and bool(retry_result.get("error"))
            if retry_has_error:
                result = retry_result
                final_status = "failed"
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
                final_status = "completed"
        else:
            workflow_steps.append({"step": "initial_run", "status": "ok"})
            if isinstance(result, dict):
                raw_status = str(result.get("status", "")).lower()
                if raw_status in {"failed", "timeout", "error"}:
                    final_status = "failed"

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        if isinstance(result, dict):
            result["workflow_steps"] = workflow_steps
            result["step_results"] = _build_step_results(agent_name, subtasks, final_status, result)
            if final_status == "completed":
                result["completion_message"] = AGENT_COMPLETION_MESSAGES.get(agent_name, "Agent workflow complete with usable results.")
            else:
                result["status"] = result.get("status") or "failed"
                result["completion_message"] = str(result.get("error") or "Agent failed before completing all steps.")

        if final_status == "completed":
            for step_idx, subtask in enumerate(subtasks, start=1):
                completion_msg = f"Step {step_idx}/{total_steps} completed: {subtask}"
                if step_idx == total_steps:
                    completion_msg = AGENT_COMPLETION_MESSAGES.get(agent_name, "Agent workflow complete with usable results.")
                await _emit_step_event(step_idx, "completed", completion_msg)
        else:
            error_message = str(result.get("error")) if isinstance(result, dict) else "Agent failed before completing all steps."
            await _emit_step_event(1, "failed", error_message)

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
            "status": "completed" if final_status == "completed" else "failed",
            "elapsed_ms": elapsed_ms,
            "result_keys": sorted(list(result.keys())) if isinstance(result, dict) else [],
            "current_step": total_steps if final_status == "completed" else 1,
            "total_steps": total_steps,
            "completion_message":
                AGENT_COMPLETION_MESSAGES.get(agent_name, "Agent workflow complete with usable results.")
                if final_status == "completed"
                else (str(result.get("error")) if isinstance(result, dict) and result.get("error") else "Agent failed before completing all steps."),
        }
        if final_status != "completed" and isinstance(result, dict) and result.get("error"):
            event["error"] = str(result.get("error"))
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
            "step_results": _build_step_results(agent_name, subtasks, "timeout", None),
        }
        await _emit_progress(
            progress_callback,
            {
                "type": "agent_status",
                "agent": agent_name,
                "status": "timeout",
                "elapsed_ms": elapsed_ms,
                "error": "Agent timed out",
                "current_step": 1,
                "total_steps": total_steps,
            },
        )
        await _emit_step_event(1, "failed", "Agent timed out before completing required steps.")
        return timeout_result
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        error_detail = f"{type(exc).__name__}: {exc}"
        failed_result = {
            "agent": agent_name,
            "error": error_detail,
            "status": "failed",
            "elapsed_ms": elapsed_ms,
            "step_results": _build_step_results(agent_name, subtasks, "failed", None),
        }
        await _emit_progress(
            progress_callback,
            {
                "type": "agent_status",
                "agent": agent_name,
                "status": "failed",
                "elapsed_ms": elapsed_ms,
                "error": error_detail,
                "current_step": 1,
                "total_steps": total_steps,
            },
        )
        await _emit_step_event(1, "failed", f"Agent failed: {error_detail}")
        return failed_result
    finally:
        if not heartbeat_task.done():
            heartbeat_task.cancel()


async def run_agents(
    tasks: list[str],
    context: dict[str, Any],
    context_by_agent: dict[str, dict[str, Any]] | None = None,
    agent_map: dict[str, AgentFn] | None = None,
    timeout_seconds: int = 90,
    progress_callback: ProgressFn | None = None,
) -> dict[str, dict[str, Any]]:
    resolved_map = agent_map or _default_agent_map()
    selected = {name: fn for name, fn in resolved_map.items() if name in tasks}

    try:
        stagger_seconds = float(os.getenv("AGENT_START_STAGGER_SECONDS", "0.45"))
    except (TypeError, ValueError):
        stagger_seconds = 0.45

    async def _run_staggered(index: int, agent_name: str, agent_fn: AgentFn) -> dict[str, Any]:
        if index > 0 and stagger_seconds > 0:
            await asyncio.sleep(index * stagger_seconds)
        scoped_context = (context_by_agent or {}).get(agent_name, context)
        return await _run_with_timeout(agent_name, agent_fn, scoped_context, timeout_seconds, progress_callback)

    results = await asyncio.gather(
        *[_run_staggered(index, name, fn) for index, (name, fn) in enumerate(selected.items())],
        return_exceptions=False,
    )

    return dict(zip(selected.keys(), results))
