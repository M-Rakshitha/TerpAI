import asyncio
import json

from backend.agents.router import run_agents
from backend.agents.task_planner import run as run_task_planner

QUERIES = [
    (
        "I need a low-budget vegan weekly food plan near UMD, upcoming campus events "
        "this weekend, and walking directions from McKeldin Library to the best dining option."
    ),
    (
        "Find research labs hiring, draft a cold email, list free study resources, and make a quick weekly schedule plan."
    ),
]


async def main() -> None:
    for query in QUERIES:
        plan = await run_task_planner(query)
        context = plan.context.model_dump()
        context["user_message"] = query
        results = await run_agents(plan.tasks, context)

        print("QUERY:", query)
        print("TASKS:", plan.tasks)
        print(
            "PLANNER_AI:",
            json.dumps(
                {
                    "ai_enrichment_used": context.get("ai_enrichment_used"),
                    "ai_routing_used": context.get("ai_routing_used"),
                    "ai_error": context.get("ai_error"),
                }
            ),
        )

        print("AGENT_AI_STATUS_BEGIN")
        for agent, output in results.items():
            data_sources = output.get("data_sources") if isinstance(output, dict) else None
            gemini_used = data_sources.get("gemini_used") if isinstance(data_sources, dict) else None

            ai_fields = {}
            if isinstance(output, dict):
                for key in [
                    "ai_recommendation",
                    "ai_summary",
                    "ai_strategy",
                    "ai_tip",
                    "cold_email",
                    "error",
                ]:
                    if key in output:
                        ai_fields[key] = output.get(key)

            print(json.dumps({"agent": agent, "gemini_used": gemini_used, "ai_fields": ai_fields}))
        print("AGENT_AI_STATUS_END")
        print("---")


if __name__ == "__main__":
    asyncio.run(main())
