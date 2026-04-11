from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import google.generativeai as genai


class GeminiClientError(RuntimeError):
    """Raised when Gemini generation fails."""


def _generate_content(prompt: str, model_name: str) -> str:
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    text = getattr(response, "text", None)
    if not text:
        raise GeminiClientError("Gemini returned an empty response")
    return text


def call_gemini(
    prompt: str,
    model: str = "gemini-3.1-flash-lite",
    timeout_seconds: int = 8,
) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiClientError("GEMINI_API_KEY is not configured")

    genai.configure(api_key=api_key)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_generate_content, prompt, model)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            raise GeminiClientError("Gemini request timed out") from exc
        except Exception as exc:
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc
