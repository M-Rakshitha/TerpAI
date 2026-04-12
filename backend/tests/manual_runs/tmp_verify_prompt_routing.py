import asyncio
import json

import httpx


async def main() -> None:
    url = "http://127.0.0.1:8016/api/query/stream"
    query = "what to have for dinner near reckord armory under $15"
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json={"message": query, "debug_trace_context": True}) as response:
            print("status", response.status_code)
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:].strip())
                event_type = event.get("type")
                if event_type == "planner_status" and event.get("status") == "completed":
                    print("tasks", event.get("tasks"))
                if event_type == "agent_status" and event.get("status") == "running":
                    ctx = event.get("context_snapshot") or {}
                    print("running", event.get("agent"), "has_agent_prompt", bool(ctx.get("agent_prompt")))
                if event_type == "query_result":
                    payload = event.get("payload", {})
                    print("agents_used", payload.get("agents_used"))
                    results = payload.get("results", {})
                    print("finance_present", bool(results.get("finance")))
                    print("dining_source", (results.get("dining") or {}).get("data_sources"))
                    break


if __name__ == "__main__":
    asyncio.run(main())
