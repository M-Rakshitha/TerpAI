from __future__ import annotations


async def run(context: dict) -> dict:
    weekly_spent = float(context.get("weekly_spent", 47.5))
    budget = context.get("budget")
    budget_remaining = float(budget) if budget is not None else max(0.0, 100.0 - weekly_spent)

    if budget is not None and float(budget) < 12:
        suggestion = "Consider dining hall options or meal swipes to stay within budget."
    else:
        suggestion = "You're on track. Your current budget can cover a standard campus dinner."

    return {
        "agent": "finance",
        "weekly_spent": round(weekly_spent, 2),
        "budget_remaining": round(budget_remaining, 2),
        "suggestion": suggestion,
    }
