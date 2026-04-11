#!/usr/bin/env python3
"""Direct invocation script for the events agent - demonstrates capabilities."""

import asyncio
from pprint import pprint

from backend.agents.events_agent import run as run_events_agent


async def main() -> None:
    print("=" * 80)
    print("EVENTS AGENT - SCENARIO 1: Career Fair Search")
    print("=" * 80)
    result = await run_events_agent(
        {
            "user_message": "I'm looking for career fair events with free food this weekend",
        }
    )
    pprint(result)

    print("\n" + "=" * 80)
    print("EVENTS AGENT - SCENARIO 2: Morning Event Discovery")
    print("=" * 80)
    result = await run_events_agent(
        {
            "user_message": "Find me social events tomorrow morning at UMD",
        }
    )
    pprint(result)

    print("\n" + "=" * 80)
    print("EVENTS AGENT - SCENARIO 3: Genre-Specific Search")
    print("=" * 80)
    result = await run_events_agent(
        {
            "user_message": "Are there any concerts or movies happening next week?",
        }
    )
    pprint(result)


if __name__ == "__main__":
    asyncio.run(main())
