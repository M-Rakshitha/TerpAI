from __future__ import annotations

import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from google import genai
from backend.utils.env_loader import load_backend_env


class GeminiClientError(RuntimeError):
    """Raised when Gemini generation fails."""


MODEL_ALIASES = {
    # Prefer 3.1 Flash Lite as requested; route to currently available model name.
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite-preview",
}

try:
    _GEMINI_MAX_REQUESTS_PER_MINUTE = max(1, int(os.getenv("GEMINI_MAX_REQUESTS_PER_MINUTE", "12")))
except (TypeError, ValueError):
    _GEMINI_MAX_REQUESTS_PER_MINUTE = 12

_GEMINI_MIN_INTERVAL_SECONDS = 60.0 / float(_GEMINI_MAX_REQUESTS_PER_MINUTE)
_GEMINI_RATE_LOCK = threading.Lock()
_GEMINI_REQUEST_TIMESTAMPS: deque[float] = deque()
_LAST_GEMINI_REQUEST_AT = 0.0


def _wait_for_gemini_rate_slot() -> None:
    global _LAST_GEMINI_REQUEST_AT
    # Process-wide limiter to keep total Gemini calls under configured rpm.
    while True:
        now = time.monotonic()
        with _GEMINI_RATE_LOCK:
            while _GEMINI_REQUEST_TIMESTAMPS and (now - _GEMINI_REQUEST_TIMESTAMPS[0]) >= 60.0:
                _GEMINI_REQUEST_TIMESTAMPS.popleft()

            window_wait = 0.0
            if len(_GEMINI_REQUEST_TIMESTAMPS) >= _GEMINI_MAX_REQUESTS_PER_MINUTE:
                window_wait = max(0.0, 60.0 - (now - _GEMINI_REQUEST_TIMESTAMPS[0]))

            spacing_wait = max(0.0, (_LAST_GEMINI_REQUEST_AT + _GEMINI_MIN_INTERVAL_SECONDS) - now)
            delay = max(window_wait, spacing_wait)

            if delay <= 0.0:
                _LAST_GEMINI_REQUEST_AT = now
                _GEMINI_REQUEST_TIMESTAMPS.append(now)
                return

        time.sleep(min(delay, 1.0) if delay > 0 else 0.01)


def _resolve_model_name(model_name: str) -> str:
    return MODEL_ALIASES.get(model_name, model_name)


def _generate_content(prompt: str, model_name: str, api_key: str) -> str:
    resolved_model = _resolve_model_name(model_name)
    with genai.Client(api_key=api_key) as client:
        response = client.models.generate_content(model=resolved_model, contents=prompt)
    text = getattr(response, "text", None)
    if not text:
        raise GeminiClientError("Gemini returned an empty response")
    return text


def call_gemini(
    prompt: str,
    model: str = "gemini-3.1-flash-lite",
    timeout_seconds: int = 8,
) -> str:
    load_backend_env()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiClientError("GEMINI_API_KEY is not configured")

    _wait_for_gemini_rate_slot()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_generate_content, prompt, model, api_key)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            raise GeminiClientError("Gemini request timed out") from exc
        except Exception as exc:
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc
