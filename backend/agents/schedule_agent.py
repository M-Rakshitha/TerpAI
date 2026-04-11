from __future__ import annotations

from datetime import datetime, timedelta


async def run(context: dict) -> dict:
    subject = context.get("subject", "General Study")
    now = datetime.now()

    return {
        "agent": "schedule",
        "study_blocks": [
            {
                "start": (now + timedelta(hours=1)).strftime("%H:%M"),
                "end": (now + timedelta(hours=3)).strftime("%H:%M"),
                "subject": subject,
                "type": "review",
            }
        ],
        "next_deadline": {
            "title": context.get("next_deadline_title", "Upcoming Assignment"),
            "due": (now + timedelta(days=1)).isoformat(),
        },
    }
