"""
Monitoring scheduler: periodically runs analysis for each watchlist symbol.

Runs as a background thread alongside the FastAPI dashboard server.
"""

import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any, Tuple

from tradingagents.monitor.watchlist import WatchlistEntry, watchlist
from tradingagents.monitor.symbols import is_tradingview_symbol
from tradingagents.monitor import store
from tradingagents.monitor import learning_config

logger = logging.getLogger(__name__)


class AnalysisResult:
    """Result from a single symbol analysis run."""

    def __init__(self, symbol: str, success: bool, signal: str, decision_text: str, error: Optional[str] = None):
        self.symbol = symbol
        self.success = success
        self.signal = signal              # "BUY" / "HOLD" / "SELL" / "UNKNOWN"
        self.decision_text = decision_text
        self.error = error
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "success": self.success,
            "signal": self.signal,
            "decision_text": self.decision_text,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


def _result_from_row(row: Dict[str, Any]) -> AnalysisResult:
    """Hydrate an AnalysisResult from a store row."""
    result = AnalysisResult(
        symbol=row["symbol"],
        success=bool(row["success"]),
        signal=row["signal"] or "UNKNOWN",
        decision_text=row["decision_text"] or "",
        error=row["error"],
    )
    ts = row.get("timestamp")
    if ts:
        try:
            result.timestamp = datetime.fromisoformat(ts)
        except (TypeError, ValueError):
            pass
    return result


def _extract_signal(final_state: Dict) -> str:
    """Extract BUY/HOLD/SELL signal from the final trading state."""
    decision = final_state.get("final_trade_decision", "") or ""
    decision_upper = decision.upper()

    for keyword in ["BUY", "SELL", "HOLD"]:
        if keyword in decision_upper:
            return keyword

    # Check trader plan too
    trader_plan = final_state.get("trader_investment_plan", "") or ""
    for keyword in ["BUY", "SELL", "HOLD"]:
        if keyword in trader_plan.upper():
            return keyword

    return "UNKNOWN"


# Matches "confidence: 0.75", "Confidence 75%", "**Confidence:** 80%" etc.
# Captures the number; group(2) is "%" only if present so we can normalise.
_CONFIDENCE_RE = re.compile(
    r"confidence[^0-9%]{0,20}(\d{1,3}(?:\.\d+)?)\s*(%)?",
    re.IGNORECASE,
)


def _parse_confidence(text: Optional[str]) -> Optional[float]:
    """Best-effort parse of a confidence score from LLM decision text. 0.0-1.0."""
    if not text:
        return None
    match = _CONFIDENCE_RE.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except (TypeError, ValueError):
        return None
    if match.group(2) == "%" or value > 1.0:
        value = value / 100.0
    if not (0.0 <= value <= 1.0):
        return None
    return value


def _apply_learned_gates(
    signal: str, decision_text: str
) -> Tuple[str, str, Optional[str]]:
    """Apply learned-param gates between the LLM and the recorded decision.

    Currently a single gate: if the decision text exposes a numeric confidence
    and it falls below ``signal_confidence_threshold``, BUY/SELL is demoted to
    HOLD. Returns ``(final_signal, annotated_decision_text, gate_reason)``.
    """
    if signal not in ("BUY", "SELL"):
        return signal, decision_text, None
    try:
        params = learning_config.load_learned_params()
    except Exception:
        return signal, decision_text, None
    threshold = params.get("signal_confidence_threshold")
    try:
        threshold = float(threshold) if threshold is not None else 0.0
    except (TypeError, ValueError):
        return signal, decision_text, None
    if threshold <= 0:
        return signal, decision_text, None
    confidence = _parse_confidence(decision_text)
    if confidence is None or confidence >= threshold:
        return signal, decision_text, None
    reason = (
        f"confidence {confidence:.2f} < signal_confidence_threshold {threshold:.2f}"
    )
    annotated = (
        f"{decision_text}\n\n[learned-gate] {signal}→HOLD: {reason}"
    )
    return "HOLD", annotated, reason


def _run_single_analysis(entry: WatchlistEntry, config: Dict, event_callback: Optional[Callable] = None) -> AnalysisResult:
    """Run analysis for one watchlist symbol. Returns AnalysisResult."""
    symbol = entry.symbol
    analysis_date = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Starting analysis for {symbol} ({entry.display_name})")

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.dataflows.config import set_config, get_config

        # Configure vendors: use TradingView for forex/commodities
        symbol_config = config.copy()
        if entry.use_tradingview:
            symbol_config["data_vendors"] = {
                "core_stock_apis": "tradingview",
                "technical_indicators": "tradingview",
                # Forex has no fundamentals or insider data
                "fundamental_data": "yfinance",
                "news_data": "yfinance",
            }

        # Build the graph with only applicable analysts
        graph = TradingAgentsGraph(
            selected_analysts=entry.analysts,
            config=symbol_config,
            debug=False,
        )

        final_state, _ = graph.propagate(symbol, analysis_date)

        signal = _extract_signal(final_state)
        decision_text = final_state.get("final_trade_decision", "No decision generated.")

        signal, decision_text, gate_reason = _apply_learned_gates(signal, decision_text)
        if gate_reason:
            logger.info("Signal gated for %s: %s", symbol, gate_reason)

        watchlist.update_result(symbol, decision_text, signal)

        result = AnalysisResult(
            symbol=symbol,
            success=True,
            signal=signal,
            decision_text=decision_text,
        )
        store.save_result(result)
        _record_ledger(result)

        logger.info(f"Analysis complete for {symbol}: {signal}")

        if event_callback:
            event_callback("analysis_complete", result.to_dict())

        return result

    except Exception as e:
        logger.error(f"Analysis failed for {symbol}: {e}", exc_info=True)
        result = AnalysisResult(
            symbol=symbol,
            success=False,
            signal="UNKNOWN",
            decision_text="",
            error=str(e),
        )
        store.save_result(result)
        _record_ledger(result)
        if event_callback:
            event_callback("analysis_error", result.to_dict())
        return result


def _record_ledger(result: AnalysisResult) -> None:
    """Append the decision to the append-only ledger for the learning loop."""
    try:
        params = learning_config.load_learned_params()
    except Exception:
        params = {}
    horizon = int(params.get("hold_horizon_hours", 24) or 24)
    try:
        store.record_decision(
            symbol=result.symbol,
            signal=result.signal,
            decision_text=result.decision_text,
            success=result.success,
            horizon_hours=horizon,
            params_snapshot=params or None,
            error=result.error,
            decided_at=result.timestamp,
        )
    except Exception as e:
        logger.warning("Failed to record decision to ledger: %s", e)


class MonitorScheduler:
    """Background scheduler that runs watchlist analysis periodically."""

    def __init__(self, check_interval_seconds: int = 60):
        """
        Args:
            check_interval_seconds: How often to check whether any symbol is due for analysis.
        """
        self.check_interval = check_interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._event_callback: Optional[Callable] = None
        self._results: Dict[str, AnalysisResult] = {}
        self._config: Dict = {}

        self._outcomes_interval = timedelta(
            minutes=int(os.getenv("TRADINGAGENTS_OUTCOMES_INTERVAL_MIN", "15"))
        )
        self._review_interval = timedelta(
            hours=int(os.getenv("TRADINGAGENTS_REVIEW_INTERVAL_HOURS", "168"))
        )
        self._last_outcomes_at: Optional[datetime] = None
        self._last_review_at: Optional[datetime] = None

    def set_config(self, config: Dict):
        """Set the LLM/app config to use for analysis runs."""
        self._config = config

    def set_event_callback(self, callback: Callable):
        """Register a callback that fires when an analysis completes."""
        self._event_callback = callback

    def start(self):
        """Start the background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="MonitorScheduler")
        self._thread.start()
        logger.info(f"MonitorScheduler started (check interval: {self.check_interval}s)")

    def stop(self):
        """Stop the background monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("MonitorScheduler stopped")

    def get_result(self, symbol: str) -> Optional[AnalysisResult]:
        """Get the latest analysis result for a symbol (reads through store)."""
        row = store.get_result(symbol)
        if not row:
            return self._results.get(symbol.upper())
        return _result_from_row(row)

    def get_all_results(self) -> Dict[str, Dict]:
        """Get all latest results as dicts (reads through store)."""
        return store.load_results()

    def trigger_now(self, symbol: str) -> Optional[AnalysisResult]:
        """Immediately run analysis for a specific symbol (blocking)."""
        entry = watchlist.get(symbol)
        if not entry:
            logger.warning(f"Symbol {symbol} not in watchlist")
            return None
        result = _run_single_analysis(entry, self._config, self._event_callback)
        self._results[symbol.upper()] = result
        return result

    def _loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                due = watchlist.due_for_analysis()
                for entry in due:
                    if not self._running:
                        break
                    result = _run_single_analysis(entry, self._config, self._event_callback)
                    self._results[entry.symbol] = result
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}", exc_info=True)

            self._tick_learning_jobs()

            # Wait before next check cycle
            for _ in range(self.check_interval):
                if not self._running:
                    return
                time.sleep(1)

    def _tick_learning_jobs(self) -> None:
        now = datetime.now()
        if self._last_outcomes_at is None or (
            now - self._last_outcomes_at >= self._outcomes_interval
        ):
            self._last_outcomes_at = now
            try:
                from tradingagents.monitor import outcomes
                n = outcomes.evaluate_pending(now=now)
                if n:
                    logger.info("Outcome evaluator processed %d decisions", n)
            except Exception as e:
                logger.warning("Outcome evaluator failed: %s", e)
        if self._last_review_at is None or (
            now - self._last_review_at >= self._review_interval
        ):
            self._last_review_at = now
            try:
                from tradingagents.monitor import reviewer
                result = reviewer.run_review()
                logger.info(
                    "Reviewer ran: applied=%s rejection=%s path=%s",
                    result.applied, result.rejection_reason, result.proposal_path,
                )
            except Exception as e:
                logger.warning("Reviewer failed: %s", e)


# Global singleton scheduler
scheduler = MonitorScheduler(check_interval_seconds=60)
