"""
Per-key exponential backoff for upstream data feeds.

Ported from HKUDS/AI-Trader's tasks.py price-failure pattern: when a feed call
fails (rate limit, network error), record it and refuse further calls for the
provider+key until a cooldown expires. Cooldown doubles on each consecutive
failure, capped, and resets on success.

In-memory only — process-local. Good enough for a single-process scheduler;
if/when state needs to survive restarts, swap _STATE for a JSON file or cache.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional, Tuple

# (provider, key) → state. Provider is e.g. "alpha_vantage:NEWS_SENTIMENT",
# key is the user-facing identifier (ticker, topic group, etc.) used in logs.
_KEY = Tuple[str, str]
_STATE: dict[_KEY, dict[str, float]] = {}
_LOCK = threading.Lock()


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _base_cooldown_s() -> int:
    return _env_int("DATAFLOW_BACKOFF_BASE_SECONDS", 60, minimum=5)


def _max_cooldown_s() -> int:
    base = _base_cooldown_s()
    return _env_int("DATAFLOW_BACKOFF_MAX_SECONDS", 3600, minimum=base)


def cooldown_remaining(provider: str, key: str) -> float:
    """Seconds left before the next call is allowed; 0 if no cooldown active."""
    with _LOCK:
        state = _STATE.get((provider, key))
        if not state:
            return 0.0
        remaining = state["retry_after"] - time.time()
        return max(0.0, remaining)


def is_in_cooldown(provider: str, key: str) -> bool:
    return cooldown_remaining(provider, key) > 0


def record_failure(provider: str, key: str) -> int:
    """Record a failure; return the cooldown (seconds) now applied."""
    now = time.time()
    base = _base_cooldown_s()
    cap = _max_cooldown_s()
    with _LOCK:
        previous = _STATE.get((provider, key), {})
        count = int(previous.get("count", 0)) + 1
        cooldown = min(cap, base * (2 ** min(count - 1, 6)))
        _STATE[(provider, key)] = {
            "count": float(count),
            "retry_after": now + cooldown,
            "last_failed_at": now,
        }
    return int(cooldown)


def record_success(provider: str, key: str) -> None:
    with _LOCK:
        _STATE.pop((provider, key), None)


class CooldownActive(Exception):
    """Raised when a caller hits a feed that is in cooldown."""

    def __init__(self, provider: str, key: str, retry_in: float):
        self.provider = provider
        self.key = key
        self.retry_in = retry_in
        super().__init__(
            f"{provider}:{key} in cooldown for {retry_in:.0f}s"
        )


def guard(provider: str, key: str) -> None:
    """Raise CooldownActive if (provider, key) is currently cooling down."""
    remaining = cooldown_remaining(provider, key)
    if remaining > 0:
        raise CooldownActive(provider, key, remaining)


def snapshot() -> dict[str, dict]:
    """Read-only view of current backoff state, for debug/admin endpoints."""
    with _LOCK:
        return {
            f"{p}:{k}": dict(v) for (p, k), v in _STATE.items()
        }
