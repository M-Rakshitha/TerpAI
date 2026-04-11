from __future__ import annotations

import asyncio

from backend.utils.gemini_client import GeminiClientError, call_gemini


def _fallback_email() -> str:
    return (
        "Subject: Prospective Undergraduate Research Assistant\n\n"
        "Hello Professor,\n"
        "I am a UMD student interested in your lab's work and would like to contribute as an undergraduate researcher. "
        "I have attached my resume and would appreciate the opportunity to discuss potential openings.\n\n"
        "Best regards,\n"
        "[Your Name]"
    )


async def _generate_cold_email(context: dict) -> str:
    prompt = (
        "Write a concise, professional cold email for a UMD student seeking a research position. "
        "Include subject line and body."
    )

    try:
        return await asyncio.to_thread(call_gemini, prompt, "gemini-3.1-flash-lite", 8)
    except GeminiClientError:
        return _fallback_email()


async def run(context: dict) -> dict:
    cold_email = await _generate_cold_email(context)

    return {
        "agent": "jobs_research",
        "jobs": [
            {
                "title": "Undergraduate Research Assistant",
                "department": "Computer Science",
                "pay": "$15/hr",
                "apply_url": "https://umd.joinhandshake.com",
            }
        ],
        "labs": [
            {
                "pi": "Dr. Example",
                "department": "Computer Science",
                "topic": "Machine Learning Systems",
                "contact": "example@umd.edu",
            }
        ],
        "cold_email": cold_email,
    }
