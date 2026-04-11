from __future__ import annotations

import json
import urllib.request


QUERIES = [
    "Find vegan dinner under $15 near AVW and route me there",
    "Find career events this weekend at UMD",
    "Plan my monthly dining and travel budget under $250",
    "Find research assistant opportunities at UMD",
]


def run_query(message: str) -> dict:
    req = urllib.request.Request(
        "http://localhost:8000/api/query",
        data=json.dumps({"message": message, "debug_trace_context": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode())


def main() -> None:
    for query in QUERIES:
        payload = run_query(query)
        outputs = payload.get("agent_outputs") or {}
        print(f"\nQUERY: {query}")
        print("agents_used:", payload.get("agents_used"))
        for name, out in outputs.items():
            if not isinstance(out, dict):
                continue
            data_sources = out.get("data_sources") or {}
            print(
                " ",
                name,
                {
                    "error": out.get("error"),
                    "gemini_used": data_sources.get("gemini_used") if isinstance(data_sources, dict) else None,
                    "web_search_used": data_sources.get("web_search_used") if isinstance(data_sources, dict) else None,
                    "has_ai_text": bool(out.get("ai_recommendation") or out.get("ai_strategy") or out.get("ai_tip")),
                },
            )


if __name__ == "__main__":
    main()
