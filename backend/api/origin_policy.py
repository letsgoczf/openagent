from __future__ import annotations

import os

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://0.0.0.0:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://0.0.0.0:8000",
)


def _split_origins(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]


def allowed_origins() -> list[str]:
    configured = _split_origins(os.getenv("OPENAGENT_ALLOWED_ORIGINS"))
    return configured or list(DEFAULT_ALLOWED_ORIGINS)


def is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    return origin.rstrip("/") in set(allowed_origins())
