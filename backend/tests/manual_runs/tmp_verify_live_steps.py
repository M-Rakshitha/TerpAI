import asyncio
import json

import httpx


async def main() -> None:
    seen_steps = 0
    seen_running = 0
    subtasks: dict[str, int] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            "http://127.0.0.1:8020/api/query/stream",
            json={"message": "what to have for dinner near reckord armory under $15", "debug_trace_context": True},
        ) as response:
            print("status", response.status_code)
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:].strip())
                if event.get("type") == "agent_status" and event.get("status") == "running":
                    seen_running += 1
                    ctx = event.get("context_snapshot") or {}
                    agent_name = event.get("agent")
                    if agent_name and agent_name not in subtasks:
                        subtasks[str(agent_name)] = len(ctx.get("agent_subtasks") or [])
                if event.get("type") == "agent_step":
                    seen_steps += 1
                if event.get("type") == "query_result":
                    payload = event.get("payload", {})
                    dining = ((payload.get("results") or {}).get("dining") or {})
                    print("agents", payload.get("agents_used"))
                    print("running_events", seen_running)
                    print("agent_step_events", seen_steps)
                    print("subtasks_seen", subtasks)
                    print("dining_step_results", len(dining.get("step_results") or []))
                    print("dining_completion_message", bool(dining.get("completion_message")))
                    break


if __name__ == "__main__":
    asyncio.run(main())
