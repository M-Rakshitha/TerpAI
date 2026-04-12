import json
import requests

BASE = "http://127.0.0.1:8000/api/query"
CASES = [
    ("Where can I find vegetarian food nearby?", {"expected_any": ["dining"], "location_sensitive": True}),
    ("What are the quiet study spots on campus?", {"expected_any": ["study_resources", "navigator", "events"]}),
    ("How do I get to the library?", {"expected_any": ["navigator"]}),
    ("What events are happening this weekend?", {"expected_any": ["events"]}),
    ("Where's the best coffee on campus?", {"expected_any": ["dining"]}),
    ("How do I register for classes?", {"expected_any": ["schedule", "study_resources"]}),
]


def main() -> None:
    rows = []
    for prompt, meta in CASES:
        payload = {"message": prompt}
        try:
            response = requests.post(BASE, json=payload, timeout=180)
            data = response.json()
        except Exception as exc:
            rows.append({"prompt": prompt, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            continue

        timeline = ((data.get("agent_execution") or {}).get("timeline") or [])
        failed = any(
            (event or {}).get("type") == "pipeline_status" and (event or {}).get("status") == "failed"
            for event in timeline
        )
        awaiting = bool(data.get("awaiting_user_input"))
        user_input_request = bool(data.get("user_input_request"))
        agents = data.get("agents_used") or []
        results = data.get("results") or {}

        if meta.get("location_sensitive") and awaiting:
            rows.append(
                {
                    "prompt": prompt,
                    "status": "skipped_location_required",
                    "agents": agents,
                    "awaiting_user_input": awaiting,
                    "user_input_request": user_input_request,
                    "highlights": (((data.get("presentation") or {}).get("summary") or {}).get("highlights") or [])[:3],
                }
            )
            continue

        result_keys = [key for key, value in results.items() if value]
        data_sources = {}
        for key, value in results.items():
            if isinstance(value, dict) and isinstance(value.get("data_sources"), dict):
                data_sources[key] = value.get("data_sources")

        expected = meta.get("expected_any", [])
        agent_match_ok = (not expected) or any(agent in agents for agent in expected)

        low_quality_flags = []
        for agent_name, agent_payload in results.items():
            if not isinstance(agent_payload, dict):
                continue
            if agent_payload.get("error"):
                low_quality_flags.append(f"{agent_name}:error")
            source_info = agent_payload.get("data_sources") if isinstance(agent_payload.get("data_sources"), dict) else {}
            seed_flag = str(source_info.get("seed_fallback") or "")
            if seed_flag:
                low_quality_flags.append(f"{agent_name}:seed_fallback={seed_flag}")
            if source_info.get("live_web_or_api_only") is False:
                low_quality_flags.append(f"{agent_name}:not_live_only")

        rows.append(
            {
                "prompt": prompt,
                "status": "ok" if (not failed and agent_match_ok and not low_quality_flags) else "needs_fix",
                "http_status": response.status_code,
                "failed": failed,
                "agents": agents,
                "expected_any": expected,
                "agent_match_ok": agent_match_ok,
                "awaiting_user_input": awaiting,
                "results_present": result_keys,
                "data_sources": data_sources,
                "low_quality_flags": low_quality_flags,
                "highlights": (((data.get("presentation") or {}).get("summary") or {}).get("highlights") or [])[:4],
            }
        )

    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
