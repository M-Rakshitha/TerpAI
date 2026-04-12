from __future__ import annotations

import pytest

from backend.agents import navigator_agent


@pytest.mark.asyncio
async def test_navigator_agent_resolves_exact_building(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        navigator_agent,
        "_fetch_map_buildings",
        lambda: [
            {
                "number": "115",
                "name_short": "AVW",
                "name_long": "A.V. Williams Building",
                "x": -76.9363383523657,
                "y": 38.99065225,
                "search_text": "115 avw a v williams building",
            }
        ],
    )
    monkeypatch.setattr(navigator_agent, "_fetch_map_suggestions", lambda query: [])
    monkeypatch.setattr(navigator_agent, "_fetch_umdio_buildings", lambda: [])

    result = await navigator_agent.run({"origin": "McKeldin Library", "destination": "A.V. Williams Building"})

    assert result["agent"] == "navigator"
    assert result["destination"] == "A.V. Williams Building"
    assert result["walk_minutes"] >= 4
    assert "google.com/maps" in result["map_url"]
    assert result["steps"]


@pytest.mark.asyncio
async def test_navigator_agent_resolves_science_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        navigator_agent,
        "_fetch_map_buildings",
        lambda: [
            {
                "number": "115",
                "name_short": "AVW",
                "name_long": "A.V. Williams Building",
                "x": -76.9363383523657,
                "y": 38.99065225,
                "search_text": "115 avw a v williams building",
            },
            {
                "number": "429",
                "name_short": "AJC",
                "name_long": "A. James Clark Hall",
                "x": -76.937724619419,
                "y": 38.9920148,
                "search_text": "429 ajc a james clark hall",
            },
            {
                "number": "037",
                "name_short": "CSI",
                "name_long": "Computer Science Instructional Center",
                "x": -76.9381,
                "y": 38.9897,
                "search_text": "37 csi computer science instructional center",
            },
        ],
    )
    monkeypatch.setattr(
        navigator_agent,
        "_fetch_map_suggestions",
        lambda query: ["Computer Science Instructional Center", "A. James Clark Hall"],
    )
    monkeypatch.setattr(navigator_agent, "_fetch_umdio_buildings", lambda: [])

    result = await navigator_agent.run({"user_message": "Where should I go for science classes?"})

    assert result["agent"] == "navigator"
    assert result["destination"] == "Computer Science Instructional Center"
    assert "google.com/maps" in result["map_url"]
    assert result.get("options")
    assert any("science" in step.lower() or "computer science" in step.lower() for step in result["steps"])


@pytest.mark.asyncio
async def test_navigator_agent_returns_error_when_query_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(navigator_agent, "_fetch_map_buildings", lambda: [])
    monkeypatch.setattr(navigator_agent, "_fetch_map_suggestions", lambda query: [])
    monkeypatch.setattr(navigator_agent, "_fetch_umdio_buildings", lambda: [])

    result = await navigator_agent.run({"user_message": ""})

    assert result["agent"] == "navigator"
    assert result["destination"] == ""
    assert result.get("error")
    assert "google.com/maps" in result["map_url"]


@pytest.mark.asyncio
async def test_navigator_agent_resolves_library_query_to_specific_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        navigator_agent,
        "_fetch_map_buildings",
        lambda: [
            {
                "number": "001",
                "name_short": "MCK",
                "name_long": "McKeldin Library",
                "x": -76.9435,
                "y": 38.9893,
                "search_text": "001 mck mckeldin library",
            },
            {
                "number": "002",
                "name_short": "ARTS",
                "name_long": "Architecture Library",
                "x": -76.9441,
                "y": 38.9879,
                "search_text": "002 arts architecture library",
            },
        ],
    )
    monkeypatch.setattr(navigator_agent, "_fetch_map_suggestions", lambda query: [])
    monkeypatch.setattr(navigator_agent, "_fetch_umdio_buildings", lambda: [])

    result = await navigator_agent.run(
        {
            "user_message": "how to get to library from here",
            "current_location_coords": {"latitude": 38.9869, "longitude": -76.9426},
        }
    )

    assert result["agent"] == "navigator"
    assert result["origin"] == "38.9869,-76.9426"
    assert result["destination"] in {"McKeldin Library", "Architecture Library"}
    assert result.get("query_destination")
    assert isinstance(result.get("top_results"), list)
    assert result.get("top_results")
    assert result["top_results"][0]["name"] in {"McKeldin Library", "Architecture Library"}
    assert "google.com/maps/dir" in result["map_url"]
    assert any(name in " ".join(result.get("steps", [])) for name in ["McKeldin Library", "Architecture Library"])


@pytest.mark.asyncio
async def test_navigator_agent_preserves_unknown_explicit_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(navigator_agent, "_fetch_map_buildings", lambda: [])
    monkeypatch.setattr(navigator_agent, "_fetch_map_suggestions", lambda query: [])
    monkeypatch.setattr(navigator_agent, "_fetch_umdio_buildings", lambda: [])

    result = await navigator_agent.run({"destination": "Quantum Cafe"})

    assert result["destination"] == "Quantum Cafe"
    assert "google.com/maps/dir" in result["map_url"]
    assert "destination=Quantum+Cafe" in result["map_url"]


@pytest.mark.asyncio
async def test_navigator_agent_falls_back_to_search_for_nearby_dietary_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(navigator_agent, "_fetch_map_buildings", lambda: [])
    monkeypatch.setattr(
        navigator_agent,
        "_fetch_map_suggestions",
        lambda query: ["NuVegan Cafe", "PLNT Burger (College Park)"] if "vegan" in query.lower() else [],
    )
    monkeypatch.setattr(navigator_agent, "_fetch_umdio_buildings", lambda: [])

    result = await navigator_agent.run({"user_message": "vegan options nearby"})

    assert result["agent"] == "navigator"
    assert result["destination"] != "vegan restaurants near current location"
    assert "google.com/maps/dir" in result["map_url"]
    assert isinstance(result.get("top_results"), list)
    assert len(result.get("top_results", [])) >= 1
    assert all(item.get("map_url") for item in result.get("top_results", []) if isinstance(item, dict))
    assert not result.get("error")


@pytest.mark.asyncio
async def test_navigator_agent_builds_start_stop_map_url_when_origin_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        navigator_agent,
        "_fetch_map_buildings",
        lambda: [
            {
                "number": "115",
                "name_short": "AVW",
                "name_long": "A.V. Williams Building",
                "x": -76.9363383523657,
                "y": 38.99065225,
                "search_text": "115 avw a v williams building",
            },
            {
                "number": "037",
                "name_short": "CSI",
                "name_long": "Computer Science Instructional Center",
                "x": -76.9381,
                "y": 38.9897,
                "search_text": "37 csi computer science instructional center",
            },
        ],
    )
    monkeypatch.setattr(
        navigator_agent,
        "_fetch_map_suggestions",
        lambda query: ["Computer Science Instructional Center"] if "science" in query.lower() else [],
    )
    monkeypatch.setattr(navigator_agent, "_fetch_umdio_buildings", lambda: [])

    result = await navigator_agent.run(
        {
            "origin": "A.V. Williams Building",
            "user_message": "Where should I go for science classes?",
        }
    )

    assert "origin=AVW" in result["map_url"]
    assert "destination=Computer+Science+Instructional+Center" in result["map_url"]


@pytest.mark.asyncio
async def test_navigator_agent_uses_umdio_building_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(navigator_agent, "_fetch_map_buildings", lambda: [])
    monkeypatch.setattr(navigator_agent, "_fetch_map_suggestions", lambda query: [])
    monkeypatch.setattr(
        navigator_agent,
        "_fetch_umdio_buildings",
        lambda: [
            {
                "number": "226",
                "name_short": "ESJ",
                "name_long": "Edward St. John Learning and Teaching Center",
                "x": -76.941914,
                "y": 38.986699,
                "search_text": "226 esj edward st john learning and teaching center",
            }
        ],
    )

    result = await navigator_agent.run({"destination": "ESJ"})
    assert result["destination"] == "Edward St. John Learning and Teaching Center"
    assert "google.com/maps" in result["map_url"]


@pytest.mark.asyncio
async def test_navigator_agent_uses_location_object_as_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        navigator_agent,
        "_fetch_map_buildings",
        lambda: [
            {
                "number": "030",
                "name_short": "STAMP",
                "name_long": "Stamp Student Union",
                "x": -76.9448,
                "y": 38.9881,
                "search_text": "030 stamp stamp student union",
            }
        ],
    )
    monkeypatch.setattr(navigator_agent, "_fetch_map_suggestions", lambda query: [])
    monkeypatch.setattr(navigator_agent, "_fetch_umdio_buildings", lambda: [])

    result = await navigator_agent.run(
        {
            "user_message": "How do I get to Stamp Student Union?",
            "location": {"lat": 38.9897, "lng": -76.9378},
        }
    )

    assert result["origin"] == "38.9897,-76.9378"
    assert "origin=38.9897%2C-76.9378" in result["map_url"]
    assert "destination=STAMP" in result["map_url"] or "destination=Stamp+Student+Union" in result["map_url"]
