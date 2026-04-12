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
    monkeypatch.setattr(
        dining_agent,
        "_query_nominatim_restaurants",
        lambda _origin_label, limit=12: [],
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
    assert result.get("warning")
    assert not result.get("error")


@pytest.mark.asyncio
async def test_dining_agent_prioritizes_closest_campus_option_for_user_location(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dining_agent,
        "_fetch_live_dining_names",
        lambda: ["South Campus Dining", "Yahentamitsi Dining Hall", "251 North Dining"],
    )
    monkeypatch.setattr(
        dining_agent,
        "_geocode_location",
        lambda _location: (38.9907, -76.9378),
    )
    monkeypatch.setattr(
        dining_agent,
        "_query_overpass_restaurants",
        lambda _lat, _lon, radius_m=2200: [],
    )

    result = await dining_agent.run(
        {
            "user_message": "Find me food near Yahentamitsi",
            "user_location": "Yahentamitsi Dining Hall",
        }
    )

    options = result.get("options", [])
    assert options
    assert options[0].get("name") == "Yahentamitsi Dining Hall"


@pytest.mark.asyncio
async def test_dining_agent_reads_budget_menu_and_dietary_from_context_aliases() -> None:
    result = await dining_agent.run(
        {
            "user_message": "Find dinner options",
            "max_budget": 14,
            "dietary_preferences": ["Vegetarian"],
            "food_preferences": ["Pizza"],
        }
    )

    basis = result.get("recommendation_basis", {})
    assert basis.get("budget") == 14.0
    assert "vegetarian" in basis.get("dietary_preferences", [])
    assert "pizza" in basis.get("menu_preferences", [])


@pytest.mark.asyncio
async def test_dining_agent_respects_selected_option_for_route_preview() -> None:
    result = await dining_agent.run(
        {
            "user_message": "Find dinner options",
            "user_location": "McKeldin Library, University of Maryland",
            "selected_option": "251 North Dining",
        }
    )

    route_preview = result.get("route_preview", {})
    assert route_preview.get("destination") == "251 North Dining"
    assert "google.com/maps/dir" in str(route_preview.get("map_url", ""))


@pytest.mark.asyncio
async def test_dining_agent_uses_origin_alias_for_location_context() -> None:
    result = await dining_agent.run(
        {
            "user_message": "Show me nearby options",
            "origin": "A.V. Williams Building",
        }
    )

    route_preview = result.get("route_preview", {})
    assert route_preview.get("origin") == "A.V. Williams Building"
    assert "google.com/maps/dir" in str(route_preview.get("map_url", ""))


@pytest.mark.asyncio
async def test_dining_agent_prioritizes_preference_matching_off_campus_option(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dining_agent, "_fetch_live_dining_names", lambda: ["South Campus Dining"])
    monkeypatch.setattr(
        dining_agent,
        "_query_overpass_restaurants",
        lambda _lat, _lon, radius_m=2200: [
            {
                "lat": 38.9870,
                "lon": -76.9425,
                "tags": {"name": "Noodle Hub", "cuisine": "noodles;asian", "diet": "vegan options"},
            }
        ],
    )

    result = await dining_agent.run(
        {
            "user_message": "Find vegan noodles around me",
            "dietary_restrictions": ["vegan"],
            "menu_preferences": ["noodles"],
            "user_location": "College Park, MD",
            "budget": 20,
        }
    )

    recommendations = result.get("menu_recommendations", [])
    assert recommendations
    assert recommendations[0].get("name") == "Noodle Hub"
    assert recommendations[0].get("source") == "off_campus"


@pytest.mark.asyncio
async def test_dining_agent_uses_nominatim_when_overpass_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dining_agent, "_fetch_live_dining_names", lambda: ["South Campus Dining"])
    monkeypatch.setattr(
        dining_agent,
        "_query_overpass_restaurants",
        lambda _lat, _lon, radius_m=2200: (_ for _ in ()).throw(RuntimeError("overpass down")),
    )
    monkeypatch.setattr(
        dining_agent,
        "_query_nominatim_restaurants",
        lambda _origin_label, limit=12: [
            {
                "display_name": "Green Bowl, College Park, Maryland",
                "lat": "38.9892",
                "lon": "-76.9387",
            }
        ],
    )

    result = await dining_agent.run(
        {
            "user_message": "Find dinner under $15 near campus",
            "budget": 15,
        }
    )

    options = result.get("options", [])
    assert options
    assert any(option.get("name") == "Green Bowl" for option in options)
    assert result.get("data_sources", {}).get("off_campus") == "nominatim_search"


@pytest.mark.asyncio
async def test_dining_agent_returns_soft_no_results_when_sources_are_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dining_agent, "_fetch_live_dining_names", lambda: [])
    monkeypatch.setattr(dining_agent, "_query_overpass_restaurants", lambda _lat, _lon, radius_m=2200: [])
    monkeypatch.setattr(dining_agent, "_build_web_menu_options", lambda _location, _budget, _menu_preferences, _dietary_preferences: ([], "none", 0))
    monkeypatch.setattr(dining_agent, "_enrich_options_with_web_evidence", lambda _options, _location, _budget, _menu_preferences: ([], 0))

    result = await dining_agent.run({"user_message": "vegan options nearby"})

    assert result["agent"] == "dining"
    assert isinstance(result.get("options"), list)
    assert result.get("options") == []
    assert result.get("data_sources", {}).get("seed_fallback") is None
    assert result.get("needs_user_input") is True
    assert result.get("warning")
    assert not result.get("error")


@pytest.mark.asyncio
async def test_dining_agent_keeps_campus_results_when_web_branch_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dining_agent,
        "_fetch_live_dining_names",
        lambda: (["South Campus Dining", "Yahentamitsi Dining Hall"], "umd_locations_page", 0),
    )
    monkeypatch.setattr(
        dining_agent,
        "_query_overpass_restaurants",
        lambda _lat, _lon, radius_m=2200: [],
    )
    monkeypatch.setattr(
        dining_agent,
        "_build_web_menu_options",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("web branch error")),
    )

    result = await dining_agent.run(
        {
            "user_message": "Where's the best coffee on campus?",
        }
    )

    assert result["agent"] == "dining"
    options = result.get("options", [])
    assert options
    assert any(option.get("name") == "South Campus Dining" for option in options)
    assert result.get("data_sources", {}).get("campus") == "umd_locations_page"


@pytest.mark.asyncio
async def test_dining_agent_coffee_near_me_uses_fastpath_off_campus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dining_agent, "_geocode_location", lambda _location: (38.9869, -76.9426))
    monkeypatch.setattr(
        dining_agent,
        "_query_overpass_restaurants",
        lambda _lat, _lon, radius_m=2200: [
            {
                "lat": 38.9872,
                "lon": -76.9418,
                "tags": {"name": "Vigilante Coffee", "cuisine": "cafe;coffee_shop"},
            }
        ],
    )

    # If these are called, fast path was not taken.
    monkeypatch.setattr(
        dining_agent,
        "_fetch_live_dining_names",
        lambda: (_ for _ in ()).throw(RuntimeError("campus branch should be skipped")),
    )
    monkeypatch.setattr(
        dining_agent,
        "_build_web_menu_options",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("web branch should be skipped")),
    )

    result = await dining_agent.run(
        {
            "user_message": "best coffee near me",
            "user_location": "38.985607126601685,-76.93969726626288",
        }
    )

    options = result.get("options", [])
    assert options
    assert options[0].get("name") == "Vigilante Coffee"
    assert result.get("data_sources", {}).get("campus") == "skipped_beverage_fastpath"
    assert result.get("data_sources", {}).get("web_menu") == "skipped_beverage_fastpath"
