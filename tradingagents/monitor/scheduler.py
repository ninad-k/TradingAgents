"""
Monitoring scheduler: periodically runs analysis for each watchlist symbol.

Runs as a background thread alongside the FastAPI dashboard server.
"""

import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any, Tuple

from tradingagents.agents.schemas import PortfolioRating
from tradingagents.agents.schemas import parse_pm_decision
from tradingagents.monitor.watchlist import WatchlistEntry, watchlist
from tradingagents.monitor.symbols import is_tradingview_symbol
from tradingagents.monitor import store
from tradingagents.monitor import learning_config
from tradingagents.monitor.live_progress import live_progress, COMPONENT_KEYS

logger = logging.getLogger(__name__)


class AnalysisResult:
    """Result from a single symbol analysis run."""

    def __init__(
        self,
        symbol: str,
        success: bool,
        signal: str,
        decision_text: str,
        error: Optional[str] = None,
        execution: Optional[Dict[str, Any]] = None,
    ):
        self.symbol = symbol
        self.success = success
        self.signal = signal              # "BUY" / "HOLD" / "SELL" / "UNKNOWN"
        self.decision_text = decision_text
        self.error = error
        self.execution = execution
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "success": self.success,
            "signal": self.signal,
            "decision_text": self.decision_text,
            "error": self.error,
            "execution": self.execution,
            "timestamp": self.timestamp.isoformat(),
        }


class AnalysisJob:
    """In-memory status for a manually triggered analysis."""

    def __init__(self, symbol: str, execute_trade: bool, timeout_seconds: int):
        self.job_id = uuid.uuid4().hex
        self.symbol = symbol.upper()
        self.execute_trade = execute_trade
        self.timeout_seconds = timeout_seconds
        self.status = "queued"
        self.message = "Queued"
        self.progress_percent = 0
        self.started_at = datetime.now()
        self.updated_at = self.started_at
        self.completed_at: Optional[datetime] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None

    def update(
        self,
        status: str,
        message: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        progress_percent: Optional[int] = None,
    ) -> None:
        self.status = status
        self.message = message
        if progress_percent is not None:
            self.progress_percent = max(0, min(100, int(progress_percent)))
        elif status in {"completed", "failed", "timeout"}:
            self.progress_percent = 100
        self.updated_at = datetime.now()
        if status in {"completed", "failed", "timeout"}:
            self.completed_at = self.updated_at
        if result is not None:
            self.result = result
        if error is not None:
            self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "symbol": self.symbol,
            "execute_trade": self.execute_trade,
            "status": self.status,
            "message": self.message,
            "progress_percent": self.progress_percent,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "timeout_seconds": self.timeout_seconds,
            "result": self.result,
            "error": self.error,
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


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _build_analysis_trace(
    final_state: Dict[str, Any],
    result: AnalysisResult,
) -> Dict[str, Any]:
    """Extract dashboard-safe component outputs from a completed graph state."""
    investment_debate = final_state.get("investment_debate_state") or {}
    risk_debate = final_state.get("risk_debate_state") or {}
    return {
        "symbol": result.symbol,
        "signal": result.signal,
        "success": result.success,
        "timestamp": result.timestamp.isoformat(),
        "components": {
            "market_analyst": _text(final_state.get("market_report")),
            "sentiment_analyst": _text(final_state.get("sentiment_report")),
            "news_analyst": _text(final_state.get("news_report")),
            "fundamentals_analyst": _text(final_state.get("fundamentals_report")),
            "bull_researcher": _text(investment_debate.get("bull_history")),
            "bear_researcher": _text(investment_debate.get("bear_history")),
            "research_manager": _text(final_state.get("investment_plan"))
            or _text(investment_debate.get("judge_decision")),
            "trader": _text(final_state.get("trader_investment_plan")),
            "aggressive_risk": _text(risk_debate.get("aggressive_history")),
            "neutral_risk": _text(risk_debate.get("neutral_history")),
            "conservative_risk": _text(risk_debate.get("conservative_history")),
            "portfolio_manager": _text(final_state.get("final_trade_decision"))
            or result.decision_text,
        },
        "debates": {
            "research": _text(investment_debate.get("history")),
            "risk": _text(risk_debate.get("history")),
        },
        "execution": result.execution,
    }


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


def _run_single_analysis(
    entry: WatchlistEntry,
    config: Dict,
    event_callback: Optional[Callable] = None,
    execute_trade: bool = False,
    allow_auto_trade_config: bool = True,
    progress_callback: Optional[Callable[[str], None]] = None,
    timeout_deadline: Optional[datetime] = None,
) -> AnalysisResult:
    """Run analysis for one watchlist symbol. Returns AnalysisResult."""
    symbol = entry.symbol
    analysis_date = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Starting analysis for {symbol} ({entry.display_name})")

    def progress(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    def timed_out() -> bool:
        return timeout_deadline is not None and datetime.now() >= timeout_deadline

    # Map the watchlist analyst codes to the dashboard's component keys so we
    # can mark non-selected analysts as "skipped" in the live flow diagram.
    analyst_to_component = {
        "market": "market_analyst",
        "social": "sentiment_analyst",
        "news": "news_analyst",
        "fundamentals": "fundamentals_analyst",
    }
    applicable = [analyst_to_component[a] for a in entry.analysts if a in analyst_to_component]
    applicable += [
        "bull_researcher", "bear_researcher", "research_manager", "trader",
        "aggressive_risk", "neutral_risk", "conservative_risk", "portfolio_manager",
    ]
    run_id = live_progress.start_run(symbol, applicable)

    try:
        live_progress.set_stage(run_id, "Preparing data and config")
        progress("Running: preparing data and config")
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.dataflows.config import set_config, get_config

        # Configure vendors. Priority chain mirrors the global default —
        # tradingview first (forex/commodity/crypto/index coverage), then MT5
        # for anything the broker has direct bars on, then yfinance as a
        # last-resort fallback. The router falls through on exceptions OR
        # error-string returns, so a TradingView outage no longer breaks the
        # whole analysis.
        symbol_config = config.copy()
        if entry.use_tradingview:
            symbol_config["data_vendors"] = {
                "core_stock_apis": "tradingview,mt5,yfinance",
                "technical_indicators": "tradingview,yfinance",
                # No corporate fundamentals or insider data for macro instruments.
                "fundamental_data": "yfinance",
                "news_data": "yfinance",
            }

        live_progress.set_stage(run_id, "Building LLM graph")
        progress("Running: building LLM graph")
        # Build the graph with only applicable analysts
        graph = TradingAgentsGraph(
            selected_analysts=entry.analysts,
            config=symbol_config,
            debug=False,
        )

        live_progress.set_stage(run_id, "Running LLM pipeline")
        progress("Running: LLM market analysis")
        final_state, _ = graph.propagate(
            symbol,
            analysis_date,
            node_callback=lambda chunk: live_progress.apply_graph_chunk(run_id, chunk),
        )
        if timed_out():
            result = AnalysisResult(
                symbol=symbol,
                success=False,
                signal="UNKNOWN",
                decision_text="",
                error=f"Analysis timed out after {config.get('analysis_timeout_seconds', 600)} seconds",
            )
            store.save_result(result)
            _record_ledger(result)
            live_progress.finish_run(run_id, "timeout", error=result.error)
            if event_callback:
                event_callback("analysis_timeout", result.to_dict())
            return result

        progress("Running: extracting signal")
        signal = _extract_signal(final_state)
        decision_text = final_state.get("final_trade_decision", "No decision generated.")

        signal, decision_text, gate_reason = _apply_learned_gates(signal, decision_text)
        if gate_reason:
            logger.info("Signal gated for %s: %s", symbol, gate_reason)

        watchlist.update_result(symbol, decision_text, signal)

        progress("Running: checking trade execution")
        execution = _maybe_execute_trade(
            symbol=symbol,
            decision_text=decision_text,
            signal=signal,
            decision_date=analysis_date,
            config=symbol_config,
            execute_trade=execute_trade,
            allow_auto_trade_config=allow_auto_trade_config,
        )

        progress("Running: recording result")
        result = AnalysisResult(
            symbol=symbol,
            success=True,
            signal=signal,
            decision_text=decision_text,
            execution=execution,
        )
        store.save_result(result)
        decision_id = _record_ledger(result)
        if decision_id is not None:
            store.save_analysis_trace(
                decision_id=decision_id,
                symbol=symbol,
                trace=_build_analysis_trace(final_state, result),
                created_at=result.timestamp,
            )

        logger.info(f"Analysis complete for {symbol}: {signal}")

        live_progress.finish_run(run_id, "success", signal=signal)
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
        live_progress.finish_run(run_id, "error", error=str(e))
        if event_callback:
            event_callback("analysis_error", result.to_dict())
        return result


def _maybe_execute_trade(
    symbol: str,
    decision_text: str,
    signal: str,
    decision_date: str,
    config: Dict[str, Any],
    execute_trade: bool = False,
    allow_auto_trade_config: bool = True,
) -> Optional[Dict[str, Any]]:
    """Optionally convert a completed TradingAgents decision into a broker order."""
    if not (execute_trade or (allow_auto_trade_config and config.get("auto_trade_enabled"))):
        return None
    if signal not in {"BUY", "SELL"}:
        return {"status": "skipped", "reason": f"Signal {signal} is not tradeable"}
    trading_mode = str(config.get("trading_mode", "paper")).lower()
    # The paper-only safety net is meant to protect against the *unattended*
    # auto-trader firing live orders by surprise. A manual "Trade" button click
    # (execute_trade=True) is an explicit user authorization in real time, so
    # we let it through. The scheduler-driven path still respects the gate.
    if not execute_trade and config.get("auto_trade_paper_only", True) and trading_mode != "paper":
        logger.info(
            "Auto-trade blocked for %s: auto_trade_paper_only is on and trading_mode=%s. "
            "Set TRADINGAGENTS_AUTO_TRADE_PAPER_ONLY=false to allow the scheduler to trade live.",
            symbol, trading_mode,
        )
        return {"status": "blocked", "reason": "Auto-trade is paper-only by default"}

    try:
        from tradingagents.brokers.mt5_connector import get_shared_mt5_connector
        from tradingagents.brokers.order_generator import OrderGenerator
        from tradingagents.brokers.risk_manager import RiskManager
        from tradingagents.brokers.execution_engine import ExecutionEngine

        decision = parse_pm_decision(decision_text)
        if signal == "BUY":
            decision.rating = PortfolioRating.BUY
        elif signal == "SELL":
            decision.rating = PortfolioRating.SELL

        connector = get_shared_mt5_connector(account_type=trading_mode)
        risk_percent = float(config.get("max_risk_per_trade_percent", 0.5) or 0.5)
        risk_usd = config.get("max_risk_per_trade_usd")
        generator = OrderGenerator(
            max_risk_percent=risk_percent,
            max_risk_usd=risk_usd,
            trade_comment=str(config.get("trade_comment") or "TradingAgent2.0"),
        )
        risk_manager = RiskManager(
            max_open_positions=int(config.get("max_open_positions", 5) or 5),
            max_risk_per_trade_percent=risk_percent,
            max_risk_per_trade_usd=risk_usd,
        )
        engine = ExecutionEngine(
            connector=connector,
            risk_manager=risk_manager,
            order_generator=generator,
            approval_mode="semi_auto",
        )
        pending = engine.process_decision(
            decision=decision,
            symbol=symbol,
            decision_date=decision_date,
        )
        if not pending:
            return {"status": "skipped", "reason": "No order generated"}
        result = engine.approve_order(pending.pending_id)
        if not result:
            return {"status": "failed", "reason": "Execution engine returned no result"}
        return {
            "status": result.status.value,
            "ticket": result.ticket,
            "execution_price": result.execution_price,
            "comment": pending.order.comment,
        }
    except Exception as e:
        logger.error("Auto-trade failed for %s: %s", symbol, e, exc_info=True)
        return {"status": "failed", "reason": str(e)}


def _record_ledger(result: AnalysisResult) -> Optional[int]:
    """Append the decision to the append-only ledger for the learning loop."""
    try:
        params = learning_config.load_learned_params()
    except Exception:
        params = {}
    horizon = int(params.get("hold_horizon_hours", 24) or 24)
    try:
        return store.record_decision(
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
    return None


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
        self._jobs: Dict[str, AnalysisJob] = {}
        self._jobs_by_symbol: Dict[str, str] = {}
        self._jobs_lock = threading.Lock()
        self._analysis_lock = threading.Lock()

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

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job else None

    def get_symbol_job(self, symbol: str) -> Optional[Dict[str, Any]]:
        with self._jobs_lock:
            job_id = self._jobs_by_symbol.get(symbol.upper())
            job = self._jobs.get(job_id) if job_id else None
            return job.to_dict() if job else None

    def _set_job_progress(self, job_id: str, message: str) -> None:
        progress_by_message = {
            "Running: queued": 5,
            "Queued: waiting for current analysis": 5,
            "Running: preparing data and config": 12,
            "Running: building LLM graph": 25,
            "Running: LLM market analysis": 55,
            "Running: extracting signal": 78,
            "Running: checking trade execution": 88,
            "Running: recording result": 95,
        }
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if not job or job.status in {"completed", "failed", "timeout"}:
                return
            job.update("running", message, progress_percent=progress_by_message.get(message))

    def _finish_job(self, job_id: str, result: AnalysisResult) -> None:
        result_dict = result.to_dict()
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if job.status == "timeout":
                return
            if result.success:
                job.update("completed", f"Completed: {result.signal}", result=result_dict, progress_percent=100)
            else:
                job.update(
                    "failed",
                    f"Failed: {result.error or 'analysis failed'}",
                    result=result_dict,
                    error=result.error,
                    progress_percent=100,
                )
            self._jobs_by_symbol[job.symbol] = job_id

    def _timeout_job(self, job_id: str) -> None:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if not job or job.status in {"completed", "failed", "timeout"}:
                return
            message = f"Analysis timed out after {job.timeout_seconds} seconds"
            job.update("timeout", message, error=message, progress_percent=100)
            self._jobs_by_symbol[job.symbol] = job_id
            symbol = job.symbol
        result = AnalysisResult(
            symbol=symbol,
            success=False,
            signal="UNKNOWN",
            decision_text="",
            error=message,
        )
        store.save_result(result)
        _record_ledger(result)
        if self._event_callback:
            self._event_callback("analysis_timeout", result.to_dict())

    def _abandon_prior_job(self, symbol: str) -> Optional[str]:
        """Mark any in-flight job + live_progress run for ``symbol`` as cancelled.

        The stuck thread will keep running until it exits naturally (Python
        threads can't be killed mid-blocking-call), but the bookkeeping is
        flipped immediately so the UI stops showing the dead status and the
        Flow page replaces the stale run with the new one.
        """
        sym_upper = symbol.upper()
        prior_job_id = self._jobs_by_symbol.get(sym_upper)
        prior_job = self._jobs.get(prior_job_id) if prior_job_id else None
        if prior_job and prior_job.status in ("queued", "running"):
            prior_job.update(
                "failed",
                "Cancelled — superseded by a new manual run",
                progress_percent=100,
            )
            logger.info("Cancelled prior job %s for %s (superseded)", prior_job_id, sym_upper)
        # Also flip any matching live_progress run so the Flow page swaps to the
        # new one instead of showing two parallel runs for the same symbol.
        for active in live_progress.get_active():
            if active.get("symbol", "").upper() == sym_upper and active.get("status") == "running":
                live_progress.finish_run(active["run_id"], "error", error="cancelled — superseded")
        return prior_job_id

    def trigger_job(
        self,
        symbol: str,
        execute_trade: bool = False,
        allow_auto_trade_config: bool = False,
        timeout_seconds: Optional[int] = None,
        force: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Start a manual analysis job in a daemon thread.

        When ``force=True``, any in-flight analysis for the same symbol is
        marked as cancelled in bookkeeping and the new run bypasses the
        global analysis lock. Useful when a previous run is stuck (slow LLM,
        broken vendor) and the user wants to retry without waiting for the
        timeout. The old thread keeps consuming whatever it was waiting on
        until its own blocking call returns — we can't preempt Python
        threads — but the UI and live_progress immediately reflect the new
        run.
        """
        entry = watchlist.get(symbol)
        if not entry:
            logger.warning(f"Symbol {symbol} not in watchlist")
            return None
        timeout = int(timeout_seconds or self._config.get("analysis_timeout_seconds", 600) or 600)
        job = AnalysisJob(symbol=symbol, execute_trade=execute_trade, timeout_seconds=timeout)

        with self._jobs_lock:
            if force:
                self._abandon_prior_job(symbol)
            queue_message = "Starting analysis" if force else "Queued: waiting for current analysis"
            job.update("queued", queue_message, progress_percent=5)
            self._jobs[job.job_id] = job
            self._jobs_by_symbol[job.symbol] = job.job_id

        def run() -> None:
            # When force=True, skip the global analysis lock so a stuck prior
            # thread can't block the new run. Otherwise serialize as before.
            if force:
                self._run_inside_analysis(job, entry, execute_trade, allow_auto_trade_config, timeout)
            else:
                with self._analysis_lock:
                    self._run_inside_analysis(job, entry, execute_trade, allow_auto_trade_config, timeout)

        threading.Thread(target=run, daemon=True, name=f"AnalysisJob-{job.symbol}").start()
        return job.to_dict()

    def _run_inside_analysis(
        self,
        job: AnalysisJob,
        entry,
        execute_trade: bool,
        allow_auto_trade_config: bool,
        timeout: int,
    ) -> None:
        """Inner body of ``trigger_job`` — extracted so the force-path can call
        it without holding ``_analysis_lock``."""
        timer = threading.Timer(timeout, self._timeout_job, args=(job.job_id,))
        timer.daemon = True
        timer.start()
        deadline = datetime.now() + timedelta(seconds=timeout)
        try:
            result = _run_single_analysis(
                entry,
                self._config,
                self._event_callback,
                execute_trade=execute_trade,
                allow_auto_trade_config=allow_auto_trade_config,
                progress_callback=lambda msg: self._set_job_progress(job.job_id, msg),
                timeout_deadline=deadline,
            )
            self._results[entry.symbol.upper()] = result
            self._finish_job(job.job_id, result)
        except Exception as e:
            logger.error("Analysis job failed for %s: %s", entry.symbol, e, exc_info=True)
            result = AnalysisResult(
                symbol=entry.symbol,
                success=False,
                signal="UNKNOWN",
                decision_text="",
                error=str(e),
            )
            store.save_result(result)
            _record_ledger(result)
            self._finish_job(job.job_id, result)
        finally:
            timer.cancel()

    def trigger_now(
        self,
        symbol: str,
        execute_trade: bool = False,
        allow_auto_trade_config: bool = False,
    ) -> Optional[AnalysisResult]:
        """Immediately run analysis for a specific symbol (blocking)."""
        entry = watchlist.get(symbol)
        if not entry:
            logger.warning(f"Symbol {symbol} not in watchlist")
            return None
        with self._analysis_lock:
            result = _run_single_analysis(
                entry,
                self._config,
                self._event_callback,
                execute_trade=execute_trade,
                allow_auto_trade_config=allow_auto_trade_config,
            )
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
                    with self._analysis_lock:
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
