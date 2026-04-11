from __future__ import annotations

import json

import requests

def main() -> None:
    url = "http://localhost:8000/api/query/stream"
    payload = {
        "message": "Find vegan dinner under $15 and route me there",
        "debug_trace_context": True,
    }

    resp = requests.post(
        url,
        json=payload,
        stream=True,
        timeout=90,
        headers={"Accept": "text/event-stream"},
    )

    print("status:", resp.status_code)
    print("stream_events:")

    events = []
    final_payload = None
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        evt = json.loads(line[6:])
        events.append(evt)
        print(
            {
                "type": evt.get("type"),
                "status": evt.get("status"),
                "agent": evt.get("agent"),
                "error": evt.get("error"),
            }
        )
        if evt.get("type") == "query_result":
            final_payload = evt.get("payload", {})
            break

    print("summary:")
    print("event_count:", len(events))
    print("has_query_result:", final_payload is not None)

    if final_payload is not None:
        print("agents_used:", final_payload.get("agents_used"))
        outs = final_payload.get("agent_outputs") or {}
        print(
            "agent_errors:",
            {k: v.get("error") for k, v in outs.items() if isinstance(v, dict) and v.get("error")},
        )


if __name__ == "__main__":
    main()
