from __future__ import annotations

import asyncio
import os
from typing import Any

from backend.utils.gemini_client import GeminiClientError, call_gemini


_GEMINI_CALL_LOCK = asyncio.Lock()
_LAST_GEMINI_CALL_TS = 0.0


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


async def _pace_gemini_calls() -> None:
    global _LAST_GEMINI_CALL_TS

    min_gap = max(0.0, _env_float("GEMINI_MIN_CALL_GAP_SECONDS", 0.9))
    fixed_delay = max(0.0, _env_float("GEMINI_FIXED_DELAY_SECONDS", 0.2))
    now = asyncio.get_running_loop().time()

    async with _GEMINI_CALL_LOCK:
        earliest = _LAST_GEMINI_CALL_TS + min_gap
        wait_seconds = max(0.0, earliest - now) + fixed_delay
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        _LAST_GEMINI_CALL_TS = asyncio.get_running_loop().time()


async def call_gemini_with_retry(
    prompt: str,
    model: str = "gemini-3.1-flash-lite",
    timeout_seconds: int = 10,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.2,
) -> str:
    configured_attempts = _env_int("GEMINI_MAX_ATTEMPTS", max_attempts)
    max_attempts = max(1, configured_attempts)
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            await _pace_gemini_calls()
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
            delay = min(base_delay_seconds * (2 ** (attempt - 1)), 10.0)
            await asyncio.sleep(delay)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = min(base_delay_seconds * (2 ** (attempt - 1)), 10.0)
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
