"""Process-wide LLM token usage tracking for the dashboard.

The CLI already has a per-run ``StatsCallbackHandler`` (``cli/stats_handler.py``),
but the live scheduler builds its graph with no callbacks, so nothing counts
tokens on the dashboard path. This module provides a thread-safe, process-wide
accumulator plus a LangChain callback that feeds it. The running total is
persisted to disk so it survives an API restart, and it powers both the
dashboard "Tokens Used" card and the auto-threshold "Stop Sonnet" kill switch.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult

_USAGE_NAME = "token_usage.json"


def _usage_path() -> Path:
    # Mirror app_settings' config dir so everything lives under ~/.tradingagents.
    base = os.environ.get(
        "TRADINGAGENTS_CONFIG_DIR",
        os.path.join(os.path.expanduser("~"), ".tradingagents", "config"),
    )
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path / _USAGE_NAME


class TokenTracker:
    """Thread-safe, process-wide accumulator of LLM token usage."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.tokens_in = 0
        self.tokens_out = 0
        self.llm_calls = 0
        self._load()

    # ── persistence ────────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            with open(_usage_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            self.tokens_in = int(data.get("tokens_in", 0))
            self.tokens_out = int(data.get("tokens_out", 0))
            self.llm_calls = int(data.get("llm_calls", 0))
        except (FileNotFoundError, ValueError, OSError):
            # Fresh start — no snapshot yet or a corrupt file.
            self.tokens_in = self.tokens_out = self.llm_calls = 0

    def _persist_locked(self) -> None:
        path = _usage_path()
        tmp = path.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "tokens_in": self.tokens_in,
                        "tokens_out": self.tokens_out,
                        "llm_calls": self.llm_calls,
                    },
                    f,
                )
            os.replace(tmp, path)
        except OSError:
            # Persistence is best-effort; never break a trading run over it.
            pass

    # ── mutation ───────────────────────────────────────────────────────────
    def record(self, input_tokens: int = 0, output_tokens: int = 0, calls: int = 0) -> None:
        with self._lock:
            self.tokens_in += int(input_tokens or 0)
            self.tokens_out += int(output_tokens or 0)
            self.llm_calls += int(calls or 0)
            self._persist_locked()

    def reset(self) -> Dict[str, Any]:
        with self._lock:
            self.tokens_in = self.tokens_out = self.llm_calls = 0
            self._persist_locked()
        return self.get_usage()

    # ── read ───────────────────────────────────────────────────────────────
    def get_usage(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "total": self.tokens_in + self.tokens_out,
                "llm_calls": self.llm_calls,
            }

    def total(self) -> int:
        with self._lock:
            return self.tokens_in + self.tokens_out

    def callback(self) -> BaseCallbackHandler:
        """Return a LangChain callback that feeds this tracker."""
        return _TokenUsageCallback(self)


class _TokenUsageCallback(BaseCallbackHandler):
    """LangChain callback that forwards token usage to a ``TokenTracker``.

    Mirrors the extraction logic in ``cli/stats_handler.py`` but writes into the
    shared process-wide tracker instead of per-run counters.
    """

    def __init__(self, tracker: TokenTracker) -> None:
        super().__init__()
        self._tracker = tracker

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        self._tracker.record(calls=1)

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[Any]], **kwargs: Any) -> None:
        self._tracker.record(calls=1)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return

        usage_metadata = None
        if hasattr(generation, "message"):
            message = generation.message
            if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                usage_metadata = message.usage_metadata

        if usage_metadata:
            self._tracker.record(
                input_tokens=usage_metadata.get("input_tokens", 0),
                output_tokens=usage_metadata.get("output_tokens", 0),
            )


_TRACKER: Optional[TokenTracker] = None
_TRACKER_LOCK = threading.Lock()


def get_token_tracker() -> TokenTracker:
    """Return the process-wide token tracker singleton."""
    global _TRACKER
    if _TRACKER is None:
        with _TRACKER_LOCK:
            if _TRACKER is None:
                _TRACKER = TokenTracker()
    return _TRACKER
