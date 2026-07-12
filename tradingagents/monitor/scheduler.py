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


# ── Mock content variant library ──────────────────────────────────────────
# Each component has multiple plausible commentary templates so consecutive
# mock runs produce visibly different narratives. `{signal}`/`{opposite}`/
# `{symbol}` placeholders are filled per run.

_MOCK_VARIANTS: Dict[str, list] = {
    "market_analyst": [
        "{symbol} price action: ascending triangle on the 4H. RSI 62, MACD bullish crossover. Volume +18 % vs 20-day avg. MT5 tick feed live.",
        "{symbol} consolidating just below resistance. RSI 54 neutral, MACD flat. ATR contracting — breakout setup forming. TradingView indicators loaded.",
        "{symbol} strong impulse leg up. Higher highs/higher lows intact. 50EMA acting as dynamic support. Volume profile shows clear value area.",
        "{symbol} reversal signal off the 200EMA. Bullish engulfing on daily, RSI exiting oversold (32 → 41). Tape reading positive.",
        "{symbol} range-bound with declining volatility. RSI 49, MACD curl. Awaiting catalyst — bias slightly {signal}-leaning given larger trend.",
    ],
    "sentiment_analyst": [
        "Social sentiment: 64 % {signal_lower}-leaning across X/Twitter. Reddit r/wallstreetbets net positive. EODHD fear/greed: 58 (neutral-greedy).",
        "Crowd sentiment skewed {signal_lower} — 71 % bullish mentions on FinTwit (24h). No viral negative narratives. Influencer chatter constructive.",
        "Sentiment mixed but tilting {signal_lower}. X engagement +22 % vs week-ago baseline. Reddit DD posts gaining traction. EODHD score: 52.",
        "Strong {signal_lower} bias in retail sentiment (67 %). Options flow shows unusual call activity. Sentiment momentum building.",
        "Sentiment neutral-to-{signal_lower}. No panic, no euphoria. Healthy positioning according to crowd-derived indicators.",
    ],
    "news_analyst": [
        "Bloomberg headline scan: no major macro shock. Fed speakers neutral-dovish. Sector news mildly supportive. Finnhub calendar clear next 24h.",
        "Reuters/Bloomberg: central-bank stance unchanged. CPI in line with expectations. Earnings season tailwind. No red-flag events on radar.",
        "News flow constructive. Geopolitical risk muted. Commodity prices stable. Finnhub event calendar clean through tomorrow's close.",
        "Macro backdrop quiet. PMI prints slightly above consensus. Dollar index sideways. News-driven volatility expected to stay subdued.",
        "Mixed news tape. One negative sector story balanced by broader risk-on flow. Net read: neutral with slight {signal_lower} skew.",
    ],
    "fundamentals_analyst": [
        "Fundamentals stable. No recent insider sells. Financial history clean. Balance sheet supports continuation of current trend.",
        "Company profile healthy. Margins expanding YoY. Insider buying in last 30 days. Fundamentals align with technical setup.",
        "Mixed fundamentals — top-line growth strong but margin compression noted. Net: neutral, defer to price action.",
        "Fundamentals improving. Recent earnings beat, guidance raised. Insider transactions net positive. Solid base for a {signal}.",
        "Fundamental picture unchanged from last review. No catalysts expected near-term. Technical-driven entry preferred.",
    ],
    "bull_researcher": [
        "Bull case: momentum, positive sentiment, and clean technicals all align for a {signal} entry. Risk/reward favourable at current levels.",
        "Bullish thesis intact: trend up, sentiment supportive, no fundamental headwinds. Asymmetric upside if breakout confirms.",
        "Bull view: macro tailwind + technical setup = high-conviction long. Stop placement clear, target 2.5R away.",
        "Bullish read on data. Volume confirmation, sector strength, oversold bounce potential. Argues for {signal} now, scale later.",
        "Bull desk: defensive positioning already in price. Setup offers favourable skew. Recommend {signal} at market with stop below structure.",
    ],
    "bear_researcher": [
        "Bear case: elevated macro uncertainty and stretched positioning argue for caution. A {opposite} or flat stance would reduce drawdown risk.",
        "Bearish counter: extended rally, RSI nearing overbought on weekly, sentiment crowded. Risk of mean reversion elevated.",
        "Bear desk: thin liquidity above current price could trigger fast unwind. Prefer to wait for pullback or fade strength.",
        "Bearish view: divergences forming on momentum indicators. Smart-money flow shifting defensive. Caution warranted.",
        "Bear thesis: late-cycle dynamics, macro fragility. {opposite} or sit-out cheaper than chasing.",
    ],
    "research_manager": [
        "Debate concluded. Bull arguments more compelling given current data. Research verdict: **{signal}** with moderate conviction.",
        "Weighing bull/bear: bull case has stronger technical support, bear case relies on macro tail. Verdict: **{signal}**, sized prudently.",
        "Research debate productive. Both sides have merit. Tilting **{signal}** based on near-term setup; revisit if {opposite} thesis materialises.",
        "After debate: bull case wins on confluence (price + sentiment + flow). **{signal}** approved with standard risk parameters.",
        "Manager note: the bear case is the longer-term tail risk; bull case is the present-day setup. Approve **{signal}** for the tactical window.",
    ],
    "trader": [
        "Plan: **{signal}** {symbol} at market. Size 1.0 % of equity. SL 1.5 %, TP 3.0 %. Hold horizon 24h.",
        "Plan: enter **{signal}** {symbol} at market. Risk 0.75 % of account. SL at structure (1.8 %), TP at 2x SL.",
        "Trade plan: **{signal}** {symbol}, 1.2 % equity, SL 1.2 %, TP 2.4 %. Trail stop to break-even at 1R.",
        "Execution plan: **{signal}** {symbol}, market order, 0.9 % risk, tiered exits at 1.5R and 3R.",
        "Trader: **{signal}** {symbol} at market, conservative 0.6 % risk given elevated vol. SL 1.0 %, TP 2.5 %.",
    ],
    "aggressive_risk": [
        "Aggressive desk: approve {signal}. High-conviction setup; willing to accept full position size.",
        "Aggressive: this is exactly the asymmetric setup we want. Approve {signal} at full size, even consider 1.25x.",
        "Aggressive risk: green light. Setup justifies full allocation. {signal} with conviction.",
        "Aggressive desk: approve {signal} at standard size — would size larger but respecting portfolio caps.",
    ],
    "neutral_risk": [
        "Neutral desk: approve {signal} at 75 % standard size. Macro tail-risk warrants slight reduction.",
        "Neutral: approve {signal}, standard size. Risk/reward acceptable, no overrides needed.",
        "Neutral risk: green-light {signal} at 80 % size. Slight haircut for prevailing vol regime.",
        "Neutral desk: approve {signal} at full size with standard stops. No adjustment to risk parameters.",
    ],
    "conservative_risk": [
        "Conservative desk: approve {signal} at 50 % size. Preserve capital; tighten stop to 1.0 %.",
        "Conservative: approve {signal} but at 40 % size with tight 0.8 % stop. Capital preservation priority.",
        "Conservative risk: scale {signal} to 60 % size, move stop closer (1.1 %). Tail risk in macro warrants caution.",
        "Conservative desk: reluctant approve {signal} at 45 % size. Prefer to deploy more after confirmation.",
    ],
}


def _build_mock_stage_data(signal: str, symbol: str, final_text: str) -> list:
    """Return per-component mock content using randomly-picked template variants."""
    import random
    opposite = "SELL" if signal == "BUY" else "BUY"
    ctx = {
        "signal": signal,
        "signal_lower": signal.lower(),
        "opposite": opposite,
        "symbol": symbol,
    }
    stages = []
    for component_key in (
        "market_analyst", "sentiment_analyst", "news_analyst", "fundamentals_analyst",
        "bull_researcher", "bear_researcher", "research_manager", "trader",
        "aggressive_risk", "neutral_risk", "conservative_risk",
    ):
        template = random.choice(_MOCK_VARIANTS[component_key])
        stages.append((component_key, template.format(**ctx)))
    stages.append(("portfolio_manager", final_text))
    return stages


def simulate_mock_pipeline(
    run_id: str,
    signal: str,
    symbol: str,
    final_text: str,
    total_duration_seconds: Optional[float] = None,
) -> None:
    """Animate all 12 pipeline stages over a random 20–30s window.

    Picks a different template per component each call, then distributes the
    total wall-clock time across stages with per-stage randomness so it feels
    like a real LLM run.
    """
    import random
    import time as _time

    total = total_duration_seconds if total_duration_seconds is not None else random.uniform(20.0, 30.0)
    stages = _build_mock_stage_data(signal, symbol, final_text)

    # Random weights → random per-stage durations summing to `total`.
    weights = [random.uniform(0.5, 1.6) for _ in stages]
    weight_sum = sum(weights) or 1.0
    delays = [(w / weight_sum) * total for w in weights]

    for (component_key, mock_content), delay in zip(stages, delays):
        live_progress.set_stage(run_id, component_key.replace("_", " ").title())
        live_progress.mark_component(run_id, component_key, "running")
        _time.sleep(max(0.2, delay))
        live_progress.mark_component(run_id, component_key, "done", mock_content)


def _run_mock_analysis(
    entry: WatchlistEntry,
    config: Dict,
    event_callback: Optional[Callable],
    execute_trade: bool,
    allow_auto_trade_config: bool,
    run_id: str,
    analysis_date: str,
    progress: Callable[[str], None],
) -> AnalysisResult:
    """Skip LLM pipeline and randomly pick BUY or SELL for testing purposes.

    Records a real decision, executes a real trade (if auto_trade is on or
    execute_trade is True), and flows data to the Scoreboard and Decisions
    screens exactly as a real analysis would.
    """
    import random
    symbol = entry.symbol
    signal = random.choice(["BUY", "SELL"])
    mock_text = (
        f"**Rating**: {signal}\n"
        f"**Confidence**: 0.85\n\n"
        f"Mock analysis — LLM pipeline bypassed for testing. Signal randomly assigned."
    )

    try:
        simulate_mock_pipeline(run_id, signal, symbol, mock_text)
        live_progress.set_stage(run_id, f"Mock {signal} — executing")
        progress(f"Mock mode: randomly selected {signal}")

        # In mock mode the whole point is to test execution — always fire the trade.
        execution = _maybe_execute_trade(
            symbol=symbol,
            decision_text=mock_text,
            signal=signal,
            decision_date=analysis_date,
            config=config,
            execute_trade=True,
            allow_auto_trade_config=False,
        )

        watchlist.update_result(symbol, mock_text, signal)

        result = AnalysisResult(
            symbol=symbol,
            success=True,
            signal=signal,
            decision_text=mock_text,
            execution=execution,
        )
        store.save_result(result)
        decision_id = _record_ledger(result)

        # Stamp entry price immediately from execution so the outcomes evaluator
        # can compute PnL without overwriting the actual fill price.
        if decision_id and execution and execution.get("execution_price"):
            try:
                from tradingagents.monitor import learning_config as _lc
                _params = {}
                try:
                    _params = _lc.load_learned_params()
                except Exception:
                    pass
                horizon = int(_params.get("hold_horizon_hours", 24) or 24)
                store.save_outcome(
                    decision_id=decision_id,
                    entry_price=execution["execution_price"],
                    exit_price=None,
                    pnl_pct=None,
                    horizon_hours=horizon,
                )
            except Exception as _e:
                logger.warning("mock analysis: could not stamp entry price: %s", _e)

        live_progress.finish_run(run_id, "success", signal=signal)
        if event_callback:
            event_callback("analysis_complete", result.to_dict())

        logger.info("Mock analysis for %s: %s (execution=%s)", symbol, signal, execution)
        return result

    except Exception as exc:
        logger.error("Mock analysis failed for %s: %s", symbol, exc, exc_info=True)
        result = AnalysisResult(
            symbol=symbol, success=False, signal="UNKNOWN",
            decision_text="", error=str(exc),
        )
        store.save_result(result)
        live_progress.finish_run(run_id, "error", error=str(exc))
        if event_callback:
            event_callback("analysis_error", result.to_dict())
        return result


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

    # ── "Stop Sonnet" kill switch + token budget ─────────────────────────────
    # Auto-latch the switch off once the running token total crosses the budget,
    # then skip the LLM pipeline entirely so no further tokens are spent. This
    # runs before start_run() so a disabled state produces no live flow entry.
    from tradingagents.monitor.token_usage import get_token_tracker
    from tradingagents.monitor import app_settings

    budget = int(config.get("token_budget_max", 0) or 0)
    if budget > 0 and config.get("llm_enabled", True) and get_token_tracker().total() >= budget:
        logger.warning(
            "Token budget %s reached; auto-disabling LLM (Stop Sonnet) for %s", budget, symbol
        )
        try:
            app_settings.update_settings({"llm_enabled": False})
        except Exception:
            logger.warning("Failed to persist llm_enabled=False after budget breach", exc_info=True)
        config = {**config, "llm_enabled": False}
    if not config.get("llm_enabled", True):
        logger.info("LLM disabled (Stop Sonnet); skipping analysis for %s", symbol)
        return AnalysisResult(
            symbol=symbol,
            success=False,
            signal="HOLD",
            decision_text="LLM analysis disabled (Stop Sonnet).",
            error="llm_disabled",
        )
    # ─────────────────────────────────────────────────────────────────────────

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

    # ── Mock mode: skip LLM entirely, randomly pick BUY/SELL ──────────────
    if config.get("mock_mode_enabled", False):
        return _run_mock_analysis(
            entry=entry,
            config=config,
            event_callback=event_callback,
            execute_trade=execute_trade,
            allow_auto_trade_config=allow_auto_trade_config,
            run_id=run_id,
            analysis_date=analysis_date,
            progress=progress,
        )
    # ──────────────────────────────────────────────────────────────────────

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

        # An explicit intraday timeframe (e.g. M1) is only honored by the
        # broker-native MT5 vendor — TradingView/yfinance use their own pickers.
        # Put MT5 first so 1-minute bars actually reach the Market Analyst.
        market_tf = str(config.get("market_timeframe", "auto") or "auto").upper()
        if market_tf not in ("", "AUTO"):
            symbol_config["data_vendors"] = {
                "core_stock_apis": "mt5,tradingview,yfinance",
                "technical_indicators": "tradingview,yfinance",
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
            callbacks=[get_token_tracker().callback()],
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
            trace = _build_analysis_trace(final_state, result)
            store.save_analysis_trace(
                decision_id=decision_id,
                symbol=symbol,
                trace=trace,
                created_at=result.timestamp,
            )
            # Persist a management-ready flow report + rolling summary.
            from tradingagents.monitor.flow_report import write_flow_report
            write_flow_report(symbol_config, result, trace, decision_id)

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
        if not connector.is_connected() and not connector.connect():
            return {"status": "blocked", "reason": "Broker connection unavailable"}

        from tradingagents.brokers.trade_guard import (
            load_mt5_setup, operational_guard, qualify_setup,
        )
        operational_ok, operational_reason = operational_guard(
            symbol=symbol,
            positions=connector.get_positions(),
            history=connector.get_trade_history(days=1, limit=100),
            max_total_volume=float(config.get("max_total_volume", 2.0)),
            cooldown_minutes=int(config.get("trade_cooldown_minutes", 15)),
            max_consecutive_losses=int(config.get("max_consecutive_losses", 3)),
            max_daily_loss_usd=float(config.get("max_daily_loss_usd", 500)),
        )
        if not operational_ok:
            return {"status": "blocked", "reason": operational_reason}

        if config.get("setup_filter_enabled", True):
            try:
                setup = load_mt5_setup(
                    symbol,
                    signal,
                    timeframe=str(config.get("market_timeframe", "M1") or "M1"),
                )
                setup_ok, setup_reason = qualify_setup(
                    setup,
                    max_spread_atr_ratio=float(config.get("max_spread_atr_ratio", 0.40)),
                    min_volume_ratio=float(config.get("min_volume_ratio", 0.20)),
                )
                if not setup_ok:
                    return {"status": "blocked", "reason": setup_reason, "setup": setup.to_dict()}
            except Exception as exc:
                return {"status": "blocked", "reason": f"Setup validation unavailable: {exc}"}
        risk_percent = float(config.get("max_risk_per_trade_percent", 0.5) or 0.5)
        risk_usd = config.get("max_risk_per_trade_usd")
        generator = OrderGenerator(
            max_risk_percent=risk_percent,
            max_risk_usd=risk_usd,
            trade_comment=str(config.get("trade_comment") or "TradingAgent2.0"),
            max_position_size=float(config.get("max_position_size", 0.5)),
            atr_stop_multiplier=float(config.get("atr_stop_multiplier", 1.25)),
        )
        risk_manager = RiskManager(
            max_open_positions=int(config.get("max_open_positions", 5) or 5),
            max_risk_per_trade_percent=risk_percent,
            max_risk_per_trade_usd=risk_usd,
            max_symbol_positions=int(config.get("max_symbol_positions", 1)),
            max_total_volume=float(config.get("max_total_volume", 2.0)),
            min_reward_cost_multiple=float(config.get("min_reward_cost_multiple", 4.0)),
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
    """Append the decision to the append-only ledger for the learning loop.

    Only records successful analyses with a real signal (BUY/SELL/HOLD).
    Failed runs and UNKNOWN signals are not actionable decisions and would
    pollute the Decisions ledger and Scoreboard metrics.
    """
    if not result.success or result.signal not in {"BUY", "SELL", "HOLD"}:
        return None
    try:
        params = learning_config.load_learned_params()
    except Exception:
        params = {}
    horizon = int(params.get("hold_horizon_hours", 24) or 24)
    confidence = _parse_confidence(result.decision_text)
    try:
        return store.record_decision(
            symbol=result.symbol,
            signal=result.signal,
            decision_text=result.decision_text,
            success=True,
            horizon_hours=horizon,
            params_snapshot=params or None,
            error=None,
            decided_at=result.timestamp,
            confidence=confidence,
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
