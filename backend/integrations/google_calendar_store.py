from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_STORE_PATH = Path(os.getenv("GOOGLE_CALENDAR_TOKEN_STORE", str(_DEFAULT_DATA_DIR / "google_calendar_tokens.json")))


def _ensure_parent() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_store() -> dict[str, Any]:
    with _lock:
        if not _STORE_PATH.is_file():
            return {}
        try:
            raw = _STORE_PATH.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}


def save_refresh_token(user_sub: str, refresh_token: str) -> None:
    _ensure_parent()
    with _lock:
        data = {}
        if _STORE_PATH.is_file():
            try:
                loaded = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                data = {}
        data[user_sub] = {"refresh_token": refresh_token}
        tmp = _STORE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(_STORE_PATH)
        try:
            _STORE_PATH.chmod(0o600)
        except OSError:
            pass


def get_refresh_token(user_sub: str) -> str | None:
    data = load_store()
    entry = data.get(user_sub)
    if not isinstance(entry, dict):
        return None
    token = entry.get("refresh_token")
    return str(token).strip() if token else None


def delete_refresh_token(user_sub: str) -> None:
    with _lock:
        data = load_store()
        if user_sub in data:
            del data[user_sub]
            _ensure_parent()
            _STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
