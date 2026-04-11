from __future__ import annotations

from backend.models.schemas import QueryResponse, QueryResults

RESULT_KEYS = [
    "schedule",
    "dining",
    "events",
    "finance",
    "navigator",
    "study_resources",
    "jobs_research",
]


def aggregate(query: str, agents_used: list[str], agent_results: dict) -> QueryResponse:
    payload = {key: None for key in RESULT_KEYS}
    payload.update({k: v for k, v in agent_results.items() if k in payload})

    return QueryResponse(
        query=query,
        agents_used=agents_used,
        results=QueryResults(**payload),
    )
