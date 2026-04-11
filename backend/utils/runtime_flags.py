from __future__ import annotations

import os


def is_truthy_env(var_name: str, default: str = "false") -> bool:
    value = str(os.getenv(var_name, default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def strict_live_mode_enabled() -> bool:
    return is_truthy_env("AGENTS_STRICT_LIVE_MODE", "false")
