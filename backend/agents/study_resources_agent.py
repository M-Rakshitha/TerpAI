from __future__ import annotations


async def run(context: dict) -> dict:
    course = context.get("course", "CMSC131")

    return {
        "agent": "study_resources",
        "tutoring": [
            {
                "service": "OMSE Tutoring",
                "subject": course,
                "schedule": "Mon-Thu 4:00 PM - 8:00 PM",
                "location": "ESJ",
            }
        ],
        "office_hours": [
            {
                "professor": "TBD",
                "course": course,
                "time": "Tue 2:00 PM - 3:00 PM",
                "room": "AVW 3208",
            }
        ],
    }
