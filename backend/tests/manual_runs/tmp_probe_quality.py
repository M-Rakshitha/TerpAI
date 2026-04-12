import json
import requests

payload = {
    "message": "what to have for dinner near reckord armory under $15",
    "debug_trace_context": True,
}

response = requests.post("http://127.0.0.1:8030/api/query", json=payload, timeout=180)
print("status", response.status_code)
obj = response.json()
dining = (obj.get("results") or {}).get("dining") or {}

print("data_sources", json.dumps(dining.get("data_sources"), ensure_ascii=True))
print("warning", dining.get("warning"))
print("has_route_preview", bool(dining.get("route_preview")))
print("has_web_refs", bool(dining.get("web_references")))
print("options_count", len(dining.get("options") or []))
print("menu_rec_count", len(dining.get("menu_recommendations") or []))

first = (dining.get("menu_recommendations") or [{}])[0]
print("first_menu_ref", (first.get("web_reference") or {}).get("url"))
print("first_under_budget_items_count", len(first.get("menu_items_under_budget") or []))
print(
    "menu_item_counts",
    [len((item.get("menu_items_under_budget") or [])) for item in (dining.get("menu_recommendations") or [])],
)
print(
    "menu_item_samples",
    [
        {
            "name": item.get("name"),
            "items": (item.get("menu_items_under_budget") or [])[:2],
        }
        for item in (dining.get("menu_recommendations") or [])[:3]
    ],
)

timeline = ((obj.get("agent_execution") or {}).get("timeline")) or []
step_events = [e for e in timeline if e.get("type") == "agent_step"]
print("agent_step_events", len(step_events))
