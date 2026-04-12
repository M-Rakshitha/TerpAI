#!/usr/bin/env python3
"""Direct invocation script for the task planner - demonstrates enrichment + routing."""

import asyncio
from pprint import pprint

from backend.agents.task_planner import run as run_task_planner


async def main() -> None:
    print("=" * 100)
    print("TASK PLANNER - SCENARIO 1: Simple Dining Query")
    print("=" * 100)
    print('Input: "Find vegan food under $15 near McKeldin"')
    print()
    result = await run_task_planner("Find vegan food under $15 near McKeldin")
    print("Task Plan:")
    pprint(result.model_dump())
    print()

    print("=" * 100)
    print("TASK PLANNER - SCENARIO 2: Multi-Agent Complex Query")
    print("=" * 100)
    print(
        'Input: "I have an exam tomorrow, need career advice, '
        'and want to find events with free food this weekend"'
    )
    print()
    result = await run_task_planner(
        "I have an exam tomorrow, need career advice, and want to find events with free food this weekend"
    )
    print("Task Plan (Multiple Agents in Parallel):")
    pprint(result.model_dump())
    print()

    print("=" * 100)
    print("TASK PLANNER - SCENARIO 3: Budget + Location Constraints")
    print("=" * 100)
    print('Input: "Cheap dinner near Engineering building, max $12"')
    print()
    result = await run_task_planner("Cheap dinner near Engineering building, max $12")
    print("Task Plan with Constraints:")
    pprint(result.model_dump())
    print()

    print("=" * 100)
    print("TASK PLANNER - SCENARIO 4: Urgent Deadline Query")
    print("=" * 100)
    print('Input: "Help! My assignment is due tomorrow morning!"')
    print()
    result = await run_task_planner("Help! My assignment is due tomorrow morning!")
    print("Task Plan (High Priority):")
    pprint(result.model_dump())
    print()

    print("=" * 100)
    print("TASK PLANNER - SCENARIO 5: Navigation + Coordination")
    print("=" * 100)
    print('Input: "How do I get to McKeldin and what events are near there?"')
    print()
    result = await run_task_planner("How do I get to McKeldin and what events are near there?")
    print("Task Plan (Multiple Location-Based Agents):")
    pprint(result.model_dump())
    print()


if __name__ == "__main__":
    asyncio.run(main())
