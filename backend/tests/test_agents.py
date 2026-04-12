import pytest

from backend.agents.aggregator import aggregate
from backend.agents import (
    dining_agent,
    events_agent,
    finance_agent,
    jobs_research_agent,
    navigator_agent,
    schedule_agent,
    study_resources_agent,
)


@pytest.mark.asyncio
async def test_dining_agent_contract() -> None:
    result = await dining_agent.run({"budget": 20})
    assert result["agent"] == "dining"
    assert "options" in result


@pytest.mark.asyncio
async def test_events_agent_contract() -> None:
    result = await events_agent.run({})
    assert result["agent"] == "events"
    assert "options" in result


@pytest.mark.asyncio
async def test_finance_agent_contract() -> None:
    result = await finance_agent.run({"budget": 25})
    assert result["agent"] == "finance"
    assert "weekly_spent" in result
    assert "budget_remaining" in result


@pytest.mark.asyncio
async def test_schedule_agent_contract() -> None:
    result = await schedule_agent.run({"subject": "CMSC131"})
    assert result["agent"] == "schedule"
    assert "study_blocks" in result
    assert "next_deadline" in result


@pytest.mark.asyncio
async def test_study_resources_agent_contract() -> None:
    result = await study_resources_agent.run({"course": "MATH141"})
    assert result["agent"] == "study_resources"
    assert "tutoring" in result
    assert "office_hours" in result


@pytest.mark.asyncio
async def test_navigator_agent_contract() -> None:
    result = await navigator_agent.run({"origin": "A", "destination": "B"})
    assert result["agent"] == "navigator"
    assert "steps" in result


@pytest.mark.asyncio
async def test_jobs_research_agent_contract() -> None:
    result = await jobs_research_agent.run({})
    assert result["agent"] == "jobs_research"
    assert "jobs" in result
    assert "labs" in result
    assert "cold_email" in result


def test_aggregator_normalizes_legacy_jobs_research_payload() -> None:
    response = aggregate(
        "find cs research opportunities",
        ["jobs_research"],
        {
            "jobs_research": {
                "agent": "jobs_research",
                "jobs": [
                    {
                        "title": "Handshake | Software Intern",
                        "link": "https://example.com/job",
                        "source": "Handshake/Career",
                    }
                ],
                "labs": [
                    {
                        "opportunity": "Machine Learning Lab",
                        "link": "https://example.com/lab",
                        "source": "Faculty/Research",
                    }
                ],
                "cold_email": "Subject: Research Interest",
            }
        },
    )

    jobs_research = response.results.jobs_research
    assert jobs_research is not None
    assert len(jobs_research.jobs) == 1
    assert jobs_research.jobs[0].apply_url == "https://example.com/job"
    assert len(jobs_research.labs) == 1
    assert jobs_research.labs[0].contact == "https://example.com/lab"
