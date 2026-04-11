from __future__ import annotations

import asyncio
from typing import Any

from backend.utils.gemini_client import GeminiClientError, call_gemini


async def call_gemini_with_retry(
    prompt: str,
    model: str = "gemini-3.1-flash-lite",
    timeout_seconds: int = 8,
    max_attempts: int = 2,
    base_delay_seconds: float = 0.9,
) -> str:
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await asyncio.to_thread(call_gemini, prompt, model, timeout_seconds)
        except GeminiClientError as exc:
            last_exc = exc
            message = str(exc).lower()
            retryable = any(
                token in message
                for token in [
                    "timed out",
                    "resource_exhausted",
                    "429",
                    "temporarily",
                    "unavailable",
                    "deadline",
                    "rate",
                ]
            )
            if not retryable or attempt >= max_attempts:
                raise
            delay = min(base_delay_seconds * (2 ** (attempt - 1)), 4.0)
            await asyncio.sleep(delay)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = min(base_delay_seconds * (2 ** (attempt - 1)), 4.0)
            await asyncio.sleep(delay)

    if isinstance(last_exc, Exception):
        raise GeminiClientError(f"Gemini retry workflow exhausted: {type(last_exc).__name__}: {last_exc}")
    raise GeminiClientError("Gemini retry workflow exhausted without details")


def step(status: str, name: str, detail: str | None = None, **meta: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status, "step": name}
    if detail:
        payload["detail"] = detail
    if meta:
        payload["meta"] = meta
    return payload
