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

    result = await navigator_agent.run({"origin": "McKeldin Library", "destination": "A.V. Williams Building"})

    assert result["agent"] == "navigator"
    assert result["destination"] == "A.V. Williams Building"
    assert result["walk_minutes"] >= 4
    assert "map.umd.edu" in result["map_url"]
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

    result = await navigator_agent.run({"user_message": "Where should I go for science classes?"})

    assert result["agent"] == "navigator"
    assert result["destination"] == "Computer Science Instructional Center"
    assert "map.umd.edu" in result["map_url"]
    assert result.get("options")
    assert any("science" in step.lower() or "computer science" in step.lower() for step in result["steps"])
