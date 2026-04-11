from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


async def stream_query(message: str, ws_url: str, debug_trace_context: bool) -> None:
    try:
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"message": message, "debug_trace_context": debug_trace_context}))
            while True:
                raw = await ws.recv()
                event = json.loads(raw)
                event_type = event.get("type", "unknown")
                ts = event.get("timestamp", "")
                status = event.get("status", "")
                agent = event.get("agent", "")
                work = event.get("work", "")

                print(f"[{_now()}] type={event_type} status={status} agent={agent}")
                if work:
                    print(f"  work: {work}")
                if event_type == "planner_status" and event.get("tasks"):
                    print(f"  tasks: {event.get('tasks')}")
                if event_type == "agent_status" and event.get("elapsed_ms") is not None:
                    print(f"  elapsed_ms: {event.get('elapsed_ms')}")
                if ts:
                    print(f"  timestamp: {ts}")
                if "context_snapshot" in event:
                    print("  context_snapshot:")
                    print(json.dumps(event.get("context_snapshot"), indent=2))

                if event_type == "query_result":
                    payload = event.get("payload", {})
                    exec_meta = payload.get("agent_execution", {})
                    timeline = exec_meta.get("timeline", []) if isinstance(exec_meta, dict) else []
                    print("\nFinal Summary")
                    print(f"  agents_used: {payload.get('agents_used')}")
                    print(f"  timeline_events: {len(timeline)}")
                    print(f"  presentation_sections: {len((payload.get('presentation') or {}).get('sections', []))}")
                    break

                if event_type == "query_error":
                    print("\nQuery error:")
                    print(json.dumps(event, indent=2))
                    break
    except ConnectionClosed as exc:
        print(f"\nStream closed by server: code={exc.code} reason={exc.reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream TerpAI agent execution events over WebSocket")
    parser.add_argument("message", help="Query to send to backend")
    parser.add_argument("--ws-url", default="ws://localhost:8000/ws/query", help="WebSocket endpoint")
    parser.add_argument("--debug-trace-context", action="store_true", help="Include context snapshots in streamed events")
    args = parser.parse_args()

    asyncio.run(stream_query(args.message, args.ws_url, args.debug_trace_context))


if __name__ == "__main__":
    main()
