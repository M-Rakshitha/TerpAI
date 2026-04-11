from __future__ import annotations


async def run(context: dict) -> dict:
    origin = context.get("origin", "McKeldin Library")
    destination = context.get("destination", "Stamp Student Union")

    return {
        "agent": "navigator",
        "origin": origin,
        "destination": destination,
        "walk_minutes": 12,
        "steps": [
            "Head southeast on Campus Dr",
            "Turn left toward Union Ln",
            "Arrive at destination",
        ],
        "map_url": "https://maps.google.com/?q=University+of+Maryland",
    }
