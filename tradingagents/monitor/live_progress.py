"""In-memory tracker for currently-running analysis pipelines.

The dashboard polls /api/analysis/active to render the AnalysisFlow page with
live per-component status while the LangGraph pipeline executes. Once a run
completes it is held briefly so the UI can show the final state, then evicted.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# Canonical component order used by both the graph and the UI diagram.
COMPONENT_KEYS: List[str] = [
    "market_analyst",
    "sentiment_analyst",
    "news_analyst",
    "fundamentals_analyst",
    "bull_researcher",
    "bear_researcher",
    "research_manager",
    "trader",
    "aggressive_risk",
    "neutral_risk",
    "conservative_risk",
    "portfolio_manager",
]

# LangGraph node display names → UI component keys.
NODE_NAME_TO_KEY: Dict[str, str] = {
    "Market Analyst": "market_analyst",
    "Social Analyst": "sentiment_analyst",
    "News Analyst": "news_analyst",
    "Fundamentals Analyst": "fundamentals_analyst",
    "Bull Researcher": "bull_researcher",
    "Bear Researcher": "bear_researcher",
    "Research Manager": "research_manager",
    "Trader": "trader",
    "Aggressive Analyst": "aggressive_risk",
    "Neutral Analyst": "neutral_risk",
    "Conservative Analyst": "conservative_risk",
    "Portfolio Manager": "portfolio_manager",
}

# State updates → which component "completes" when these keys land.
STATE_KEY_TO_COMPONENT: Dict[str, str] = {
    "market_report": "market_analyst",
    "sentiment_report": "sentiment_analyst",
    "news_report": "news_analyst",
    "fundamentals_report": "fundamentals_analyst",
    "trader_investment_plan": "trader",
    "final_trade_decision": "portfolio_manager",
}

# How long a finished run sticks around in the active list before eviction.
_RETAIN_FINISHED_SECONDS = 8.0


def _now() -> float:
    return time.time()


def _summarize(text: str, limit: int = 160) -> str:
    if not text:
        return ""
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 3]}..."


class _Run:
    __slots__ = (
        "run_id",
        "symbol",
        "started_at",
        "finished_at",
        "status",
        "stage_label",
        "active_component",
        "components",
        "error",
        "signal",
        "applicable",
    )

    def __init__(self, run_id: str, symbol: str, applicable: List[str]):
        now = _now()
        self.run_id = run_id
        self.symbol = symbol
        self.started_at = now
        self.finished_at: Optional[float] = None
        self.status = "running"
        self.stage_label = "Initializing"
        self.active_component: Optional[str] = None
        self.error: Optional[str] = None
        self.signal: Optional[str] = None
        self.applicable = applicable
        self.components: Dict[str, Dict] = {
            key: {
                "status": "pending" if key in applicable else "skipped",
                "preview": "",
                "full_text": "",
                "updated_at": now,
                "started_at": None,
                "completed_at": None,
            }
            for key in COMPONENT_KEYS
        }

    def to_dict(self) -> Dict:
        return {
            "run_id": self.run_id,
            "symbol": self.symbol,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "stage_label": self.stage_label,
            "active_component": self.active_component,
            "error": self.error,
            "signal": self.signal,
            "elapsed_seconds": (self.finished_at or _now()) - self.started_at,
            "components": self.components,
        }


# Per-component stall threshold. If no component update happens for this long
# while a run is still marked "running", the watchdog declares it stalled and
# finishes it as an error. Keeps a single hung tool call or runaway LLM loop
# from holding the full per-analysis budget (up to TRADINGAGENTS_ANALYSIS_TIMEOUT_SECONDS).
_DEFAULT_STALL_SECONDS = 180


class LiveProgressTracker:
    """Thread-safe registry of in-flight analysis runs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: Dict[str, _Run] = {}
        self._stall_seconds = _DEFAULT_STALL_SECONDS
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_stop = threading.Event()

    # --- lifecycle --------------------------------------------------------

    def start_run(self, symbol: str, applicable_components: List[str]) -> str:
        run_id = uuid.uuid4().hex[:12]
        run = _Run(run_id=run_id, symbol=symbol, applicable=applicable_components)
        with self._lock:
            self._runs[run_id] = run
        return run_id

    def set_stage(self, run_id: str, label: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run.stage_label = label

    def mark_component(
        self,
        run_id: str,
        component_key: str,
        status: str,
        preview: str = "",
    ) -> None:
        if component_key not in COMPONENT_KEYS:
            return
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            entry = run.components.setdefault(
                component_key,
                {
                    "status": "pending",
                    "preview": "",
                    "full_text": "",
                    "updated_at": _now(),
                    "started_at": None,
                    "completed_at": None,
                },
            )
            entry["status"] = status
            if preview:
                # Keep both shapes: the truncated preview drives the node card,
                # the full text powers the detail panel.
                entry["preview"] = _summarize(preview)
                entry["full_text"] = preview.strip()
            entry["updated_at"] = _now()
            if status == "running":
                if not entry.get("started_at"):
                    entry["started_at"] = _now()
                run.active_component = component_key
            elif status in ("done", "failed"):
                entry["completed_at"] = _now()
                # Defensive: if the component went straight to terminal without
                # ever being marked running (e.g. fast cache hit) backfill the
                # start timestamp from updated_at so duration math still works.
                if not entry.get("started_at"):
                    entry["started_at"] = entry["updated_at"]
            elif status == "done" and run.active_component == component_key:
                run.active_component = None

    def apply_graph_chunk(self, run_id: str, chunk: Dict) -> None:
        """Translate a LangGraph stream chunk into component status updates."""
        if not chunk:
            return
        for node_name, updates in chunk.items():
            key = NODE_NAME_TO_KEY.get(node_name)
            preview = ""
            if isinstance(updates, dict):
                for state_key, comp_key in STATE_KEY_TO_COMPONENT.items():
                    if state_key in updates and updates[state_key]:
                        text = str(updates[state_key])
                        self.mark_component(run_id, comp_key, "done", text)
                        if not key:
                            key = comp_key
                        preview = text
                # Debate histories — surface partial bull/bear/risk content.
                debate = updates.get("investment_debate_state")
                if isinstance(debate, dict):
                    if debate.get("bull_history"):
                        self.mark_component(run_id, "bull_researcher", "done", str(debate["bull_history"]))
                    if debate.get("bear_history"):
                        self.mark_component(run_id, "bear_researcher", "done", str(debate["bear_history"]))
                    if debate.get("judge_decision"):
                        self.mark_component(run_id, "research_manager", "done", str(debate["judge_decision"]))
                risk = updates.get("risk_debate_state")
                if isinstance(risk, dict):
                    if risk.get("aggressive_history"):
                        self.mark_component(run_id, "aggressive_risk", "done", str(risk["aggressive_history"]))
                    if risk.get("neutral_history"):
                        self.mark_component(run_id, "neutral_risk", "done", str(risk["neutral_history"]))
                    if risk.get("conservative_history"):
                        self.mark_component(run_id, "conservative_risk", "done", str(risk["conservative_history"]))
            if key:
                self.mark_component(run_id, key, "done", preview)
                self.set_stage(run_id, node_name)

    def finish_run(
        self,
        run_id: str,
        status: str,
        signal: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run.status = status
            run.signal = signal
            run.error = error
            run.finished_at = _now()
            run.active_component = None
            # Any component still "pending" or "running" → mark as skipped/failed.
            for key, entry in run.components.items():
                if entry["status"] == "running":
                    entry["status"] = "done" if status == "success" else "failed"
                elif entry["status"] == "pending" and status != "success":
                    entry["status"] = "skipped"

    # --- watchdog ---------------------------------------------------------

    def start_watchdog(self, stall_seconds: int = _DEFAULT_STALL_SECONDS, poll_seconds: int = 15) -> None:
        """Start a daemon thread that fails runs which haven't updated in a while.

        Idempotent — calling more than once is a no-op. Reads stall_seconds
        from the ``TRADINGAGENTS_STALL_SECONDS`` env var when present so it
        can be tuned without code changes.
        """
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return
        import os
        try:
            env_stall = int(os.getenv("TRADINGAGENTS_STALL_SECONDS", "") or 0)
            if env_stall > 0:
                stall_seconds = env_stall
        except ValueError:
            pass
        self._stall_seconds = stall_seconds
        self._watchdog_stop.clear()

        def loop() -> None:
            while not self._watchdog_stop.is_set():
                self._sweep_stalled()
                self._watchdog_stop.wait(poll_seconds)

        self._watchdog_thread = threading.Thread(
            target=loop, daemon=True, name="LiveProgressWatchdog"
        )
        self._watchdog_thread.start()
        logger.info(
            "Live-progress watchdog started: stall threshold=%ds, poll=%ds",
            stall_seconds, poll_seconds,
        )

    def stop_watchdog(self) -> None:
        self._watchdog_stop.set()

    def _sweep_stalled(self) -> None:
        """Finish any run whose most-recent component update is too old."""
        now = _now()
        cutoff = now - self._stall_seconds
        stalled: List[tuple] = []
        with self._lock:
            for rid, run in self._runs.items():
                if run.status != "running":
                    continue
                # Newest signal of life across all components.
                last = max(
                    (entry.get("updated_at") or 0 for entry in run.components.values()),
                    default=run.started_at,
                )
                if last <= cutoff:
                    stalled.append((rid, run.active_component, now - last))
        for rid, active, idle in stalled:
            stage = f"stalled — no progress for {idle:.0f}s"
            if active:
                stage += f" (last active: {active})"
            logger.warning("Watchdog cancelling stalled run %s — %s", rid, stage)
            self.finish_run(rid, "error", error=stage)

    def clear_all_stalled(self) -> int:
        """Immediately cancel all running analyses that haven't updated recently.

        Used by the dashboard Clear button to force cleanup of stuck runs.
        Returns count of runs that were cancelled.
        """
        self._sweep_stalled()
        with self._lock:
            return sum(1 for r in self._runs.values() if r.status == "error")

    # --- read -------------------------------------------------------------

    def get_active(self) -> List[Dict]:
        cutoff = _now() - _RETAIN_FINISHED_SECONDS
        with self._lock:
            # Evict runs that have been finished longer than retain window.
            for rid in [
                rid
                for rid, r in self._runs.items()
                if r.finished_at is not None and r.finished_at < cutoff
            ]:
                self._runs.pop(rid, None)
            return [r.to_dict() for r in self._runs.values()]


# Module-level singleton used by the scheduler + dashboard API.
live_progress = LiveProgressTracker()
