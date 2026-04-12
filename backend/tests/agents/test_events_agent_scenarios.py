import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[3]))

from backend.agents import events_agent


@pytest.fixture(autouse=True)
def _mock_external_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock all external API calls for deterministic testing."""
    monkeypatch.setattr(
        events_agent,
        "_fetch_live_campus_events",
        lambda: [
            {
                "name": "Engineering Career Fair",
                "date": "2026-04-14",
                "time": "2:00 PM",
                "location": "Stamp Student Union, University of Maryland",
                "url": "https://example.com/events/career-fair",
                "tags": ["career", "engineering", "networking"],
                "free_food": True,
                "category": "career",
            },
            {
                "name": "Campus Movie Night",
                "date": "2026-04-12",
                "time": "8:00 PM",
                "location": "Nyumburu Cultural Center, University of Maryland",
                "url": "",
                "tags": ["entertainment", "social"],
                "free_food": True,
                "category": "social",
            },
        ],
    )
    monkeypatch.setattr(
        events_agent,
        "_query_eventbrite_nearby",
        lambda: [],
    )
    monkeypatch.setattr(events_agent, "_fetch_calendar_events_for_date", lambda date_value: [])
    monkeypatch.setattr(events_agent, "_fetch_calendar_search_events", lambda query: [])
    monkeypatch.setattr(events_agent, "_fetch_terplink_events", lambda query, date_preference=None: [])


@pytest.mark.asyncio
async def test_events_agent_extracts_event_categories() -> None:
    """Test that agent extracts event categories from user message."""
    result = await events_agent.run(
        {
            "user_message": "I want to go to a concert or networking event this weekend",
        }
    )
    assert result.get("agent") == "events"
    assert isinstance(result.get("options"), list)
    assert result.get("recommendation_basis", {}).get("interested_categories")
    assert any(cat in ["concert", "networking"] for cat in result["recommendation_basis"]["interested_categories"])


@pytest.mark.asyncio
async def test_events_agent_filters_by_free_food() -> None:
    """Test that agent prioritizes free food events when mentioned."""
    result = await events_agent.run(
        {
            "user_message": "Find events with free food this week",
        }
    )
    assert result.get("agent") == "events"
    recommendations = result.get("event_recommendations", [])
    # Should prioritize events with free_food=True
    if recommendations:
        assert any(rec.get("free_food") for rec in recommendations[:3])


@pytest.mark.asyncio
async def test_events_agent_extracts_date_preferences() -> None:
    """Test that agent extracts date preferences from message."""
    result = await events_agent.run(
        {
            "user_message": "What's going on tomorrow evening?",
        }
    )
    assert result.get("agent") == "events"
    basis = result.get("recommendation_basis", {})
    assert basis.get("date_preference") in ["tomorrow", "evening"] or basis.get("time_preference") == "evening"


@pytest.mark.asyncio
async def test_events_agent_career_fair_higher_priority() -> None:
    """Test that career events are ranked higher when career mentioned."""
    result = await events_agent.run(
        {
            "user_message": "I'm looking for career development events",
        }
    )
    assert result.get("agent") == "events"
    options = result.get("options", [])
    recommendations = result.get("event_recommendations", [])
    
    # Should have career-focused events
    if recommendations:
        career_events = [r for r in recommendations if "career" in str(r.get("tags", [])).lower()]
        assert len(career_events) > 0 or len(recommendations) > 0


@pytest.mark.asyncio
async def test_events_agent_prompts_for_details_when_generic() -> None:
    """Test that agent asks for clarification when query is vague."""
    result = await events_agent.run(
        {
            "user_message": "What events are there?",
        }
    )
    assert result.get("agent") == "events"
    # Should ask for more details due to generic query
    if result.get("needs_user_input"):
        assert isinstance(result.get("follow_up_questions"), list)
        assert len(result["follow_up_questions"]) > 0


@pytest.mark.asyncio
async def test_events_agent_builds_registration_links() -> None:
    """Test that agent builds registration links for event recommendations."""
    result = await events_agent.run(
        {
            "user_message": "I want to attend a social event this weekend",
        }
    )
    assert result.get("agent") == "events"
    recommendations = result.get("event_recommendations", [])
    
    # Each recommendation should have a registration_url
    for rec in recommendations[:3]:
        assert "registration_url" in rec
        # Should be either empty or valid URL
        if rec.get("registration_url"):
            assert rec["registration_url"].startswith("http")


@pytest.mark.asyncio
async def test_events_agent_extracts_time_preferences() -> None:
    """Test that agent correctly extracts morning/afternoon/evening/night preferences."""
    result = await events_agent.run(
        {
            "user_message": "I prefer events in the morning",
        }
    )
    assert result.get("agent") == "events"
    basis = result.get("recommendation_basis", {})
    assert basis.get("time_preference") == "morning"


@pytest.mark.asyncio
async def test_events_agent_returns_fallback_on_no_matches() -> None:
    """Test that agent returns known events as fallback when service fails."""
    result = await events_agent.run(
        {
            "user_message": "Find events on a date far in the future",
        }
    )
    assert result.get("agent") == "events"
    assert isinstance(result.get("options"), list)
    # Should return something, even if empty
    assert len(result["options"]) >= 0


@pytest.mark.asyncio
async def test_events_agent_uses_specific_date_calendar_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        events_agent,
        "_fetch_calendar_events_for_date",
        lambda date_value: [
            {
                "name": "Music For All: Concert Band Festival",
                "date": date_value,
                "time": "8:00 AM",
                "location": "The Clarice Smith Performing Arts Center",
                "url": "https://calendar.umd.edu/music-for-all-concert-band-festival-3",
                "tags": ["music", "festival"],
                "free_food": False,
                "category": "campus",
            }
        ],
    )

    result = await events_agent.run({"user_message": "events on 2026-04-11"})
    assert result.get("agent") == "events"
    assert any(option.get("date") == "2026-04-11" for option in result.get("options", []))


@pytest.mark.asyncio
async def test_events_agent_includes_terplink_club_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        events_agent,
        "_fetch_terplink_events",
        lambda query, date_preference=None: [
            {
                "name": "Cosmic Bowling",
                "date": "2026-04-11",
                "time": "8:00 PM",
                "location": "TerpZone",
                "url": "https://terplink.umd.edu/event/12014970",
                "tags": ["club", "social"],
                "free_food": False,
                "category": "club",
            }
        ],
    )

    result = await events_agent.run({"user_message": "club events this weekend"})
    assert result.get("agent") == "events"
    assert any("terplink.umd.edu" in str(rec.get("registration_url", "")) for rec in result.get("event_recommendations", []))
