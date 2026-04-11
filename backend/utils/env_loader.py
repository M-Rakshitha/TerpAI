from __future__ import annotations

import os
import sys
from pathlib import Path

_LOADED = False


def load_backend_env() -> None:
    global _LOADED
    if _LOADED:
        return

    # Tests should control their own environment explicitly.
    if "pytest" in sys.modules:
        _LOADED = True
        return

    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / "backend" / ".env"
    if not env_path.exists():
        _LOADED = True
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # Keep shell/env-provided values as source of truth.
        os.environ.setdefault(key, value)

    _LOADED = True
