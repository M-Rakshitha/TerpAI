import asyncio
import json

import httpx


async def main() -> None:
    async with httpx.AsyncClient(timeout=90.0) as client:
        async with client.stream(
            "POST",
            "http://127.0.0.1:8020/api/query/stream",
            json={"message": "what to have for dinner near reckord armory under $15", "debug_trace_context": True},
        ) as response:
            print("status", response.status_code)
            saw_result = False
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:].strip())
                if event.get("type") == "query_result":
                    saw_result = True
                    payload = event.get("payload", {})
                    dining = (payload.get("results", {}) or {}).get("dining") or {}
                    print("agents_used", payload.get("agents_used"))
                    print("dining_error", dining.get("error"))
                    print("dining_warning", dining.get("warning"))
                    print("options_head", [o.get("name") for o in (dining.get("options") or [])[:5]])
                    wf = dining.get("workflow_steps") or []
                    print("workflow_statuses", [f"{s.get('step')}:{s.get('status')}" for s in wf])
                    break
            if not saw_result:
                print("query_result_missing", True)


if __name__ == "__main__":
    asyncio.run(main())
