from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from google import genai
from backend.utils.env_loader import load_backend_env


class GeminiClientError(RuntimeError):
    """Raised when Gemini generation fails."""


MODEL_ALIASES = {
    # Prefer 3.1 Flash Lite as requested; route to currently available model name.
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite-preview",
}


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

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_generate_content, prompt, model, api_key)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            raise GeminiClientError("Gemini request timed out") from exc
        except Exception as exc:
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc
