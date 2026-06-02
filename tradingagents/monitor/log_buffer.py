"""
In-memory circular log buffer.

Captures the last N log records emitted by anything in the
``tradingagents`` namespace (and a few helpful third-party loggers) so the
dashboard can show "what is the backend actually doing right now" without
the user having to tail a file. Wired into the standard ``logging`` machinery
as a regular ``Handler``; install once at app startup.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Deque, Dict, List, Optional


_DEFAULT_CAPACITY = 500


class _RingBufferHandler(logging.Handler):
    """Logging handler that retains the most-recent N records in memory."""

    def __init__(self, capacity: int = _DEFAULT_CAPACITY):
        super().__init__()
        self._lock = threading.Lock()
        self._records: Deque[Dict] = deque(maxlen=capacity)
        self.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            entry = {
                "ts": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "formatted": self.format(record),
            }
            with self._lock:
                self._records.append(entry)
        except Exception:
            # Logging must never crash the caller.
            self.handleError(record)

    def snapshot(
        self,
        limit: int = 200,
        min_level: Optional[str] = None,
        contains: Optional[str] = None,
    ) -> List[Dict]:
        """Return the most-recent records (oldest first) optionally filtered."""
        level_no = getattr(logging, (min_level or "").upper(), 0) if min_level else 0
        needle = (contains or "").lower() or None
        with self._lock:
            items = list(self._records)
        if level_no:
            items = [i for i in items if logging.getLevelName(i["level"]) >= level_no]
        if needle:
            items = [i for i in items if needle in i["formatted"].lower()]
        if limit > 0:
            items = items[-limit:]
        return items


# Module-level singleton.
log_buffer = _RingBufferHandler()


def install_log_buffer(level: int = logging.INFO) -> None:
    """Attach the buffer to the root logger. Idempotent — safe to call twice."""
    root = logging.getLogger()
    # Only attach once.
    if log_buffer in root.handlers:
        return
    log_buffer.setLevel(level)
    root.addHandler(log_buffer)
    # If the root level is too noisy to filter at, lower the floor so this
    # handler can still see INFO records.
    if root.level == 0 or root.level > level:
        root.setLevel(level)
