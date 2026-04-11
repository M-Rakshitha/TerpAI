import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[3]))

from backend.agents import finance_agent


@pytest.fixture(autouse=True)
def _mock_web_search(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_search(query: str, max_results: int = 5) -> list[dict]:
        lowered = query.lower()
        if "dining" in lowered:
            return [
                {
                    "title": "College Park Budget Meals",
                    "url": "https://example.com/dining",
                    "snippet": "Meals around $12 and $15 near campus.",
                    "price_points": [12.0, 15.0],
                }
            ]
        if "travel" in lowered:
            return [
                {
                    "title": "Transit Costs",
                    "url": "https://example.com/travel",
                    "snippet": "Typical fares are $3 to $5 per ride.",
                    "price_points": [3.0, 5.0],
                }
            ]
        if "classes" in lowered:
            return [
                {
                    "title": "Textbook Cost Guide",
                    "url": "https://example.com/classes",
                    "snippet": "Books can be around $45 used.",
                    "price_points": [45.0],
                }
            ]
        return []

    monkeypatch.setattr(finance_agent, "_search_web_cost_signals", _fake_search)


@pytest.mark.asyncio
async def test_finance_agent_builds_budget_plan_for_weekly_student_spend() -> None:
    result = await finance_agent.run(
        {
            "user_message": "Plan a weekly dining, travel, and classes budget under $120",
            "budget": 120,
        }
    )

    assert result.get("agent") == "finance"
    assert result.get("timeframe") == "weekly"
    assert result.get("budget") == 120
    assert result.get("data_sources", {}).get("web_search_used") is True

    plan = result.get("spending_plan", [])
    categories = [item.get("category") for item in plan]
    assert "dining" in categories
    assert "travel" in categories
    assert "classes" in categories


@pytest.mark.asyncio
async def test_finance_agent_supports_budget_without_dollar_symbol() -> None:
    result = await finance_agent.run(
        {
            "user_message": "Can you plan my monthly travel and events spending under 200",
        }
    )

    assert result.get("agent") == "finance"
    assert result.get("timeframe") == "monthly"
    assert result.get("budget") == 200
    assert isinstance(result.get("suggestion"), str)


@pytest.mark.asyncio
async def test_finance_agent_returns_references_per_category() -> None:
    result = await finance_agent.run(
        {
            "user_message": "Help me budget dining and classes this week",
            "budget": 90,
        }
    )

    plan = result.get("spending_plan", [])
    assert plan
    for item in plan:
        assert "references" in item
        assert isinstance(item.get("references"), list)
