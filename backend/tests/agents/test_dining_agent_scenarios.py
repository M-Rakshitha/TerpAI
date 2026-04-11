import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[3]))

from backend.agents import dining_agent


@pytest.fixture(autouse=True)
def _mock_external_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dining_agent,
        "_fetch_live_dining_names",
        lambda: ["South Campus Dining", "Yahentamitsi Dining Hall", "251 North Dining"],
    )
    monkeypatch.setattr(
        dining_agent,
        "_geocode_location",
        lambda _location: (38.9869, -76.9426),
    )
    monkeypatch.setattr(
        dining_agent,
        "_query_overpass_restaurants",
        lambda _lat, _lon, radius_m=2200: [],
    )


@pytest.mark.asyncio
async def test_dining_agent_prompts_for_location_when_missing() -> None:
    result = await dining_agent.run(
        {
            "user_message": "Find halal dinner under $20 near UMD",
            "budget": 20,
            "dietary_restrictions": ["halal"],
        }
    )

    assert result["agent"] == "dining"
    assert isinstance(result.get("options"), list)
    assert result.get("needs_user_input") is True
    assert isinstance(result.get("follow_up_questions"), list)
    assert result["follow_up_questions"]


@pytest.mark.asyncio
async def test_dining_agent_builds_route_preview_with_user_location() -> None:
    result = await dining_agent.run(
        {
            "user_message": "I want vegan dinner",
            "budget": 18,
            "dietary_restrictions": ["vegan"],
            "user_location": "McKeldin Library, University of Maryland",
        }
    )

    route_preview = result.get("route_preview")
    assert isinstance(route_preview, dict)
    assert route_preview.get("origin") == "McKeldin Library, University of Maryland"
    assert "google.com/maps/dir" in str(route_preview.get("map_url", ""))


@pytest.mark.asyncio
async def test_dining_agent_marks_budget_ok_false_for_low_budget() -> None:
    result = await dining_agent.run(
        {
            "user_message": "I need dinner with $8 budget",
            "budget": 8,
        }
    )

    options = result.get("options", [])
    assert options
    assert any(option.get("budget_ok") is False for option in options)


@pytest.mark.asyncio
async def test_dining_agent_extracts_preferences_from_message() -> None:
    result = await dining_agent.run(
        {
            "user_message": "I want vegan noodles under $15 around campus",
        }
    )

    basis = result.get("recommendation_basis", {})
    assert basis.get("budget") == 15.0
    assert "vegan" in basis.get("dietary_preferences", [])
    assert "noodles" in basis.get("menu_preferences", [])


@pytest.mark.asyncio
async def test_dining_agent_uses_off_campus_candidates_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dining_agent, "_fetch_live_dining_names", lambda: ["South Campus Dining"])
    monkeypatch.setattr(
        dining_agent,
        "_geocode_location",
        lambda _location: (38.9869, -76.9426),
    )
    monkeypatch.setattr(
        dining_agent,
        "_query_overpass_restaurants",
        lambda _lat, _lon, radius_m=2200: [
            {
                "lat": 38.9870,
                "lon": -76.9425,
                "tags": {"name": "Noodle House", "cuisine": "noodles;asian", "diet:vegan": "yes"},
            },
            {
                "lat": 38.9880,
                "lon": -76.9430,
                "tags": {"name": "Budget Bites", "cuisine": "fast_food"},
            },
        ],
    )

    result = await dining_agent.run(
        {
            "user_message": "Find vegan noodles near me",
            "user_location": "College Park, MD",
            "dietary_restrictions": ["vegan"],
            "menu_preferences": ["noodles"],
            "budget": 16,
        }
    )

    recommendations = result.get("menu_recommendations", [])
    names = [entry.get("name") for entry in recommendations]
    assert "Noodle House" in names


@pytest.mark.asyncio
async def test_dining_agent_falls_back_when_sources_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dining_agent,
        "_fetch_live_dining_names",
        lambda: (_ for _ in ()).throw(RuntimeError("campus source down")),
    )
    monkeypatch.setattr(
        dining_agent,
        "_query_overpass_restaurants",
        lambda _lat, _lon, radius_m=2200: (_ for _ in ()).throw(RuntimeError("off-campus source down")),
    )

    result = await dining_agent.run({"user_message": "Find food"})

    assert result["agent"] == "dining"
    assert isinstance(result.get("options"), list)
    assert result["options"]
