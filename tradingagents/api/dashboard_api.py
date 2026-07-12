"""FastAPI backend for trading dashboard."""

import logging
import os
from typing import List, Dict, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from pydantic import BaseModel, Field
import asyncio
import json

from tradingagents.api.models import (
    DashboardStatus, Trade, Position, AccountStatus, TradeDirection, TradeStatus, TokenUsage
)
from tradingagents.brokers.analytics import ExecutionAnalytics
from tradingagents.brokers.mt5_connector import get_shared_mt5_connector
from tradingagents.brokers.models import OrderAction
from tradingagents.dataflows.config import get_config
from tradingagents.monitor.watchlist import watchlist
from tradingagents.monitor.scheduler import scheduler

logger = logging.getLogger(__name__)


class CodexAnalysisSubmission(BaseModel):
    """A completed analysis produced by the local Codex desktop task."""

    symbol: str
    signal: str
    decision_text: str
    components: Dict[str, str] = Field(default_factory=dict)
    execute_trade: bool = True


def _build_token_usage(config: Dict) -> TokenUsage:
    """Assemble the dashboard token-usage block from the shared tracker + settings."""
    from tradingagents.monitor.token_usage import get_token_tracker
    from tradingagents.monitor import app_settings

    usage = get_token_tracker().get_usage()
    try:
        settings = app_settings.load_settings()
    except Exception:
        settings = {}
    budget = int(settings.get("token_budget_max", config.get("token_budget_max", 0)) or 0)
    enabled = bool(settings.get("llm_enabled", config.get("llm_enabled", True)))
    return TokenUsage(
        tokens_in=usage["tokens_in"],
        tokens_out=usage["tokens_out"],
        total=usage["total"],
        llm_calls=usage["llm_calls"],
        budget_max=budget,
        llm_enabled=enabled,
    )


class DashboardManager:
    """Manages dashboard data and WebSocket connections."""

    def __init__(self):
        self.analytics = ExecutionAnalytics()
        self.connections: List[WebSocket] = []
        self._analysis_events: List[Dict] = []
        self.connector = get_shared_mt5_connector()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(self.connections)}")

    async def broadcast(self, message: Dict):
        if not self.connections:
            return
        message_json = json.dumps(message, default=str)
        dead = []
        for conn in self.connections:
            try:
                await conn.send_text(message_json)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.connections.remove(conn)

    def record_analysis_event(self, event_type: str, data: Dict):
        """Called by scheduler when an analysis completes."""
        self._analysis_events.append({"type": event_type, "data": data, "timestamp": datetime.utcnow().isoformat()})
        # Keep last 100 events
        if len(self._analysis_events) > 100:
            self._analysis_events = self._analysis_events[-100:]

    def get_dashboard_status(self) -> DashboardStatus:
        config = get_config()
        trading_mode = config.get("trading_mode", "paper")

        if not self.connector.is_connected():
            self.connector.connect()

        broker_account = self.connector.get_account_info()
        positions = self._get_dashboard_positions()
        trades = self._get_dashboard_trades()
        closed_trades = [t for t in trades if t.status == TradeStatus.CLOSED]
        wins = [t.pnl or 0.0 for t in closed_trades if (t.pnl or 0.0) > 0]
        losses = [t.pnl or 0.0 for t in closed_trades if (t.pnl or 0.0) < 0]
        win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 0.0
        total_pnl = sum(t.pnl or 0.0 for t in closed_trades) + sum(p.unrealized_pnl for p in positions)
        balance = broker_account.balance if broker_account else 10000.0

        account = AccountStatus(
            trading_mode=trading_mode,
            server=broker_account.server if broker_account else None,
            account_balance=balance,
            account_equity=broker_account.equity if broker_account else balance,
            available_margin=broker_account.free_margin if broker_account else balance,
            total_pnl=total_pnl,
            total_pnl_percent=(total_pnl / balance * 100.0) if balance else 0.0,
            win_rate=win_rate,
            total_trades=len(trades),
            open_trades=len(positions),
            closed_trades=len(closed_trades),
            largest_win=max(wins) if wins else 0.0,
            largest_loss=min(losses) if losses else 0.0,
            avg_trade_duration=self._avg_duration_seconds(trades),
        )

        return DashboardStatus(
            timestamp=datetime.utcnow(),
            connected=True,
            account=account,
            open_positions=positions,
            recent_trades=trades,
            total_positions=len(positions),
            total_closed_trades=len(closed_trades),
            token_usage=_build_token_usage(config),
        )

    def _get_dashboard_positions(self) -> List[Position]:
        now = datetime.utcnow()
        broker_positions = self.connector.get_positions()
        return [
            Position(
                symbol=pos.symbol,
                quantity=pos.volume,
                entry_price=pos.entry_price,
                current_price=pos.current_price,
                direction=TradeDirection.LONG if pos.type == OrderAction.BUY else TradeDirection.SHORT,
                unrealized_pnl=pos.profit,
                unrealized_pnl_percent=pos.profit_percent,
                entry_time=pos.open_time,
                duration_seconds=max(0, int((now - pos.open_time).total_seconds())),
                comment=pos.open_comment,
            )
            for pos in broker_positions
        ]

    def _get_dashboard_trades(self) -> List[Trade]:
        now = datetime.utcnow()
        broker_trades = self.connector.get_trade_history(days=7, limit=50)
        trades = []
        for trade in broker_trades:
            direction = TradeDirection.LONG if trade.action == OrderAction.BUY else TradeDirection.SHORT
            status = TradeStatus.CLOSED if trade.status == "closed" else TradeStatus.OPEN
            reference_time = trade.exit_time or trade.entry_time
            duration = max(0, int((now - reference_time).total_seconds()))
            trades.append(
                Trade(
                    symbol=trade.symbol,
                    entry_price=trade.entry_price,
                    entry_time=trade.entry_time,
                    exit_price=trade.exit_price,
                    exit_time=trade.exit_time,
                    quantity=trade.volume,
                    direction=direction,
                    status=status,
                    pnl=trade.profit,
                    pnl_percent=None,
                    duration_seconds=duration,
                    reason=trade.comment,
                    comment=trade.comment,
                )
            )
        # Newest first so callers can take [:N] and get the most recent N trades.
        trades.sort(key=lambda t: t.entry_time or datetime.min, reverse=True)
        return trades

    @staticmethod
    def _avg_duration_seconds(trades: List[Trade]) -> int:
        durations = [t.duration_seconds for t in trades if t.duration_seconds is not None]
        return int(sum(durations) / len(durations)) if durations else 0


dashboard_manager = DashboardManager()


def _result_uses_active_model(result: Dict, config: Dict) -> bool:
    """Hide stale model-not-found results from models no longer configured."""
    error = str(result.get("error") or "")
    if "model" not in error.lower() or "not found" not in error.lower():
        return True
    active_models = {
        str(config.get("deep_think_llm") or ""),
        str(config.get("quick_think_llm") or ""),
        str(config.get("fallback_deep_think_llm") or ""),
        str(config.get("fallback_quick_think_llm") or ""),
    }
    return any(model and model in error for model in active_models)


def _get_enriched_watchlist() -> List[Dict]:
    """Return watchlist rows with latest result and active job status."""
    entries = watchlist.to_dict_list()
    results = scheduler.get_all_results()
    config = get_config()
    for entry in entries:
        sym = entry["symbol"]
        result = results.get(sym)
        if result and _result_uses_active_model(result, config):
            entry["latest_result"] = result
        job = scheduler.get_symbol_job(sym)
        if job and job.get("status") in {"queued", "running", "completed", "failed", "timeout"}:
            entry["analysis_job"] = job
    return entries


def _on_analysis_event(event_type: str, data: Dict):
    """Scheduler callback — record event for next WebSocket broadcast."""
    dashboard_manager.record_analysis_event(event_type, data)


def _in_process_scheduler_enabled(config: Dict) -> bool:
    """Run the scheduler in-process unless explicitly disabled (for separate worker)."""
    if os.getenv("WATCHLIST_DISABLE_IN_PROCESS", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    return bool(config.get("watchlist_enabled", True))


async def _run_local_codex_schedule(interval_seconds: int, symbols: List[str]) -> None:
    """Trigger the localhost Codex strategy periodically without Anthropic."""
    from urllib.request import Request as UrlRequest, urlopen

    async def trigger(symbol: str) -> None:
        def post() -> None:
            url = f"http://127.0.0.1:8000/api/codex/run/{symbol}?execute_trade=true"
            request = UrlRequest(url, data=b"", method="POST")
            with urlopen(request, timeout=120) as response:
                response.read()
        await asyncio.to_thread(post)

    while True:
        await asyncio.sleep(interval_seconds)
        for symbol in symbols:
            try:
                await trigger(symbol)
                logger.info("Scheduled Codex strategy completed for %s", symbol)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled Codex strategy failed for %s", symbol)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the watchlist scheduler alongside the API."""
    config = get_config()

    scheduler.set_event_callback(_on_analysis_event)
    scheduler.set_config(config)
    scheduler.check_interval = int(config.get("watchlist_check_interval_seconds", scheduler.check_interval))

    if _in_process_scheduler_enabled(config):
        scheduler.start()
        logger.info("Watchlist scheduler started (in-process)")
    else:
        logger.info(
            "In-process watchlist scheduler disabled — "
            "expecting `python -m tradingagents.monitor.worker` to run separately."
        )

    # Start the stall watchdog so a hung LLM/tool call can't lock a run
    # forever. Threshold defaults to 180s but reads TRADINGAGENTS_STALL_SECONDS.
    from tradingagents.monitor.live_progress import live_progress
    live_progress.start_watchdog()

    # Capture recent log records into an in-memory ring so /api/logs can
    # surface "what is the backend actually doing" without tailing a file.
    from tradingagents.monitor.log_buffer import install_log_buffer
    install_log_buffer()

    codex_task = None
    codex_interval = int(os.getenv("CODEX_STRATEGY_INTERVAL_SECONDS", "0") or 0)
    codex_symbols = [s.strip().upper() for s in os.getenv("CODEX_STRATEGY_SYMBOLS", "BTCUSD").split(",") if s.strip()]
    if codex_interval > 0 and codex_symbols:
        codex_task = asyncio.create_task(_run_local_codex_schedule(codex_interval, codex_symbols))
        logger.info("Local Codex strategy scheduled every %ss for %s", codex_interval, ", ".join(codex_symbols))

    logger.info("Trading Dashboard API started")
    yield

    if codex_task is not None:
        codex_task.cancel()
        try:
            await codex_task
        except asyncio.CancelledError:
            pass

    live_progress.stop_watchdog()
    scheduler.stop()
    logger.info("Trading Dashboard API stopped")


app = FastAPI(
    title="Trading Dashboard API",
    description="Real-time trading dashboard with TradingView watchlist monitoring",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS: allow any localhost dev server (Vite, Next, CRA, preview, etc.)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ─── Account / Status ──────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status() -> DashboardStatus:
    return dashboard_manager.get_dashboard_status()


@app.get("/api/trades")
async def get_trades(limit: int = 50) -> List[Dict]:
    return [trade.model_dump(mode="json") for trade in dashboard_manager._get_dashboard_trades()[:limit]]


@app.get("/api/portfolio")
async def get_portfolio() -> Dict:
    metrics = dashboard_manager.analytics.get_performance_metrics()
    outcomes = dashboard_manager.analytics.get_decision_outcomes()
    return {
        "open_positions": [
            position.model_dump(mode="json")
            for position in dashboard_manager._get_dashboard_positions()
        ],
        "total_executions": metrics['executions'],
        "approval_rate": metrics['approval_rate'],
        "by_symbol": metrics['by_symbol'],
        "decision_outcomes": outcomes,
    }


@app.get("/api/analytics")
async def get_analytics() -> Dict:
    metrics = dashboard_manager.analytics.get_performance_metrics()
    outcomes = dashboard_manager.analytics.get_decision_outcomes()
    return {
        "metrics": metrics,
        "outcomes": outcomes,
        "total_actions": metrics['total_actions'],
        "approval_rate": f"{metrics['approval_rate']:.1f}%",
    }


# ─── Broker symbol catalog ─────────────────────────────────────────────────

@app.get("/api/symbols")
async def get_broker_symbols(refresh: bool = False) -> Dict:
    """Return all symbols the connected broker exposes.

    Cached on the connector after the first call so the 2500+ symbol payload
    isn't re-fetched on every request. Pass ``refresh=true`` to force a
    fresh snapshot — useful if the broker's symbol tree was edited mid-session.
    """
    try:
        symbols = dashboard_manager.connector.list_symbols(refresh=refresh)
    except Exception as e:
        logger.error("Failed to list broker symbols: %s", e)
        raise HTTPException(status_code=503, detail=f"broker unreachable: {e}")
    categories: Dict[str, int] = {}
    for s in symbols:
        cat = s.get("category") or "Other"
        categories[cat] = categories.get(cat, 0) + 1
    return {
        "count": len(symbols),
        "categories": categories,
        "symbols": symbols,
    }


# ─── Watchlist ─────────────────────────────────────────────────────────────

@app.get("/api/watchlist")
async def get_watchlist() -> List[Dict]:
    """Get all monitored symbols with their latest signals."""
    return _get_enriched_watchlist()


@app.post("/api/watchlist/{symbol}")
async def add_to_watchlist(
    symbol: str,
    interval_hours: int = 4,
    interval_minutes: Optional[int] = None,
    include_news: bool = False,
) -> Dict:
    """Add a symbol to the watchlist."""
    if interval_minutes is not None:
        interval_minutes = max(1, interval_minutes)
        interval_hours = 0 if interval_minutes < 60 else round(interval_minutes / 60)
    entry = watchlist.add(
        symbol.upper(),
        interval_hours,
        include_news,
        interval_minutes=interval_minutes,
    )
    return {"added": True, "symbol": entry.symbol, "mode": entry.mode}


@app.delete("/api/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str) -> Dict:
    """Remove a symbol from the watchlist."""
    removed = watchlist.remove(symbol.upper())
    if not removed:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")
    return {"removed": True, "symbol": symbol.upper()}


@app.post("/api/watchlist/{symbol}/analyze")
async def trigger_analysis(
    symbol: str,
    execute_trade: bool = False,
    force: bool = False,
) -> Dict:
    """Manually trigger an analysis for a watchlist symbol.

    When ``force=true``, any in-flight job for the same symbol is cancelled
    and the new run bypasses the per-process analysis lock, letting the user
    recover from a stuck run without waiting for its timeout.
    """
    entry = watchlist.get(symbol.upper())
    if not entry:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist. Add it first.")

    config = get_config()
    job = scheduler.trigger_job(
        symbol.upper(),
        execute_trade=execute_trade,
        timeout_seconds=int(config.get("analysis_timeout_seconds", 600) or 600),
        force=force,
    )
    if not job:
        raise HTTPException(status_code=500, detail=f"Could not start analysis for {symbol}")
    return {
        "triggered": True,
        "symbol": symbol.upper(),
        "execute_trade": execute_trade,
        "job_id": job["job_id"],
        "job": job,
        "message": "Analysis running in background",
    }


@app.post("/api/codex/analysis")
async def submit_codex_analysis(payload: CodexAnalysisSubmission, request: Request) -> Dict:
    """Record a local Codex analysis trace and optionally execute its verdict.

    This bridge deliberately accepts requests only from localhost.  It lets the
    Codex desktop task drive the existing Flow, ledger, risk-manager, and demo
    broker pipeline without pretending that the desktop session is an API key.
    """
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Codex bridge is localhost-only")

    from tradingagents.monitor import store
    from tradingagents.monitor.live_progress import live_progress, COMPONENT_KEYS
    from tradingagents.monitor.scheduler import AnalysisResult, _maybe_execute_trade, _record_ledger

    symbol = payload.symbol.strip().upper()
    signal = payload.signal.strip().upper()
    if not symbol or signal not in {"BUY", "SELL", "HOLD"}:
        raise HTTPException(status_code=422, detail="symbol and BUY/SELL/HOLD signal are required")
    if watchlist.get(symbol) is None:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")

    unknown = set(payload.components) - set(COMPONENT_KEYS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown Flow components: {sorted(unknown)}")

    run_id = live_progress.start_run(symbol, list(COMPONENT_KEYS))
    for key in COMPONENT_KEYS:
        content = payload.components.get(key, "No separate output supplied by Codex.")
        live_progress.set_stage(run_id, key.replace("_", " ").title())
        live_progress.mark_component(run_id, key, "running")
        live_progress.mark_component(run_id, key, "done", content)

    config = get_config()
    execution = _maybe_execute_trade(
        symbol=symbol,
        decision_text=payload.decision_text,
        signal=signal,
        decision_date=datetime.now().strftime("%Y-%m-%d"),
        config=config,
        execute_trade=payload.execute_trade,
        allow_auto_trade_config=False,
    )
    result = AnalysisResult(
        symbol=symbol,
        success=True,
        signal=signal,
        decision_text=payload.decision_text,
        execution=execution,
    )
    watchlist.update_result(symbol, payload.decision_text, signal)
    store.save_result(result)
    decision_id = _record_ledger(result)
    trace = {
        "symbol": symbol,
        "signal": signal,
        "success": True,
        "timestamp": result.timestamp.isoformat(),
        "components": payload.components,
        "execution": execution,
        "source": "codex-desktop",
    }
    if decision_id is not None:
        store.save_analysis_trace(decision_id, symbol, trace, result.timestamp)

    live_progress.finish_run(run_id, "success", signal=signal)
    dashboard_manager.record_analysis_event("analysis_complete", result.to_dict())
    return {
        "accepted": True,
        "source": "codex-desktop",
        "run_id": run_id,
        "decision_id": decision_id,
        "result": result.to_dict(),
    }


@app.post("/api/codex/run/{symbol}")
async def run_codex_strategy(symbol: str, request: Request, execute_trade: bool = False) -> Dict:
    """Run the credential-free local Codex strategy used by dashboard buttons."""
    from dataclasses import replace
    from tradingagents.brokers.trade_guard import load_mt5_setup, qualify_setup

    symbol = symbol.strip().upper()
    if watchlist.get(symbol) is None:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")
    config = get_config()
    try:
        buy = load_mt5_setup(symbol, "BUY", str(config.get("market_timeframe", "M1") or "M1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Broker setup analysis failed: {exc}") from exc
    sell = replace(buy, signal="SELL")
    gate_args = {
        "max_spread_atr_ratio": float(config.get("max_spread_atr_ratio", 0.40)),
        "min_volume_ratio": float(config.get("min_volume_ratio", 0.20)),
    }
    buy_ok, buy_reason = qualify_setup(buy, **gate_args)
    sell_ok, sell_reason = qualify_setup(sell, **gate_args)
    signal = "BUY" if buy_ok else "SELL" if sell_ok else "HOLD"
    chosen_reason = buy_reason if buy_ok else sell_reason if sell_ok else f"BUY: {buy_reason}; SELL: {sell_reason}"
    target = buy.price + 2 * buy.atr if signal == "BUY" else buy.price - 2 * buy.atr if signal == "SELL" else None
    trend = f"EMA9 {buy.ema_fast:.2f}, EMA21 {buy.ema_slow:.2f}, EMA50 {buy.ema_trend:.2f}"
    market = (
        f"{symbol} {config.get('market_timeframe', 'M1')}: price {buy.price:.2f}; {trend}; "
        f"RSI14 {buy.rsi:.1f}; ATR {buy.atr:.2f}; spread {buy.spread:.2f}; "
        f"volume {buy.volume_ratio:.2f}x average. Gate: {chosen_reason}."
    )
    components = {
        "market_analyst": market,
        "sentiment_analyst": "Short-horizon sentiment is inferred conservatively from broker price participation; no unsupported social signal overrides the gate.",
        "news_analyst": "The local dashboard run is credential-free and does not invent a news catalyst; broker-native setup quality controls execution.",
        "fundamentals_analyst": "For this M1 crypto decision, structural fundamentals are secondary to liquidity, volatility, and transaction costs.",
        "bull_researcher": f"BUY qualification: {buy_reason}.",
        "bear_researcher": f"SELL qualification: {sell_reason}.",
        "research_manager": f"Deterministic research verdict: {signal}. {chosen_reason}.",
        "trader": f"{signal}. " + (f"Target approximately {target:.2f}; risk engine controls size and stop." if target else "No order while qualification fails."),
        "aggressive_risk": "Directional opportunity may exist, but it cannot bypass liquidity, spread, or exposure controls.",
        "neutral_risk": f"Apply 0.1% risk, 0.5-lot cap, ATR stop, and 4x reward/cost gate. Current verdict: {signal}.",
        "conservative_risk": "Prefer HOLD whenever trend, momentum, volume, freshness, and cost checks are not simultaneously satisfied.",
        "portfolio_manager": f"Final {signal}. {chosen_reason}.",
    }
    decision = (
        f"**Rating**: {signal.title()}\n\n"
        f"**Executive Summary**: {signal}. {chosen_reason}. "
        "Execution remains subject to all portfolio and broker risk controls.\n\n"
        f"**Investment Thesis**: {market}\n\n"
        + (f"**Price Target**: {target:.2f}\n\n" if target is not None else "")
        + "**Time Horizon**: 15-60 minutes\n\n"
        + f"**Confidence**: {0.65 if signal != 'HOLD' else 0.85:.2f}"
    )
    return await submit_codex_analysis(
        CodexAnalysisSubmission(
            symbol=symbol,
            signal=signal,
            decision_text=decision,
            components=components,
            execute_trade=bool(execute_trade),
        ),
        request,
    )


@app.get("/api/jobs/{job_id}")
async def get_analysis_job(job_id: str) -> Dict:
    """Get manual analysis job status."""
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@app.get("/api/watchlist/{symbol}/result")
async def get_symbol_result(symbol: str) -> Dict:
    """Get the latest analysis result for a specific symbol."""
    result = scheduler.get_result(symbol.upper())
    if not result:
        raise HTTPException(status_code=404, detail=f"No result yet for {symbol}")
    return result.to_dict()


@app.get("/api/events")
async def get_events(limit: int = 20) -> List[Dict]:
    """Get recent analysis events."""
    return dashboard_manager._analysis_events[-limit:]


@app.get("/api/logs")
async def get_recent_logs(
    limit: int = 200,
    level: Optional[str] = None,
    contains: Optional[str] = None,
) -> Dict:
    """Recent backend log records from the in-memory ring buffer.

    Useful for "what is the analysis pipeline actually doing" — surfaces
    which tool calls fired, which LLM model was hit, which vendor returned
    what, and any stack traces.

    Query params:
    - limit: max records to return (default 200)
    - level: minimum severity — DEBUG/INFO/WARNING/ERROR/CRITICAL
    - contains: case-insensitive substring filter on the formatted line
    """
    from tradingagents.monitor.log_buffer import log_buffer
    records = log_buffer.snapshot(limit=limit, min_level=level, contains=contains)
    return {"count": len(records), "records": records}


@app.get("/api/analysis/active")
async def get_active_analysis_runs() -> List[Dict]:
    """Currently running analysis pipelines with per-component status.

    Polled by the AnalysisFlow page to render a live architecture diagram while
    the LangGraph executes. Finished runs linger ~8s for the UI to show the
    completed state before being evicted.
    """
    from tradingagents.monitor.live_progress import live_progress
    return live_progress.get_active()


@app.post("/api/analysis/clear-stuck")
async def clear_stuck_runs() -> Dict[str, int]:
    """Immediately force the watchdog to scan for and cancel stalled runs.

    Returns count of runs that were cancelled.
    """
    from tradingagents.monitor.live_progress import live_progress
    cleared = live_progress.clear_all_stalled()
    return {"cleared": cleared}


_MOCK_PROPOSAL_TEMPLATES = [
    {
        "key": "min_confidence",
        "old": 0.60, "new": 0.65,
        "rationale": "Recent {signal} signals under 0.65 confidence underperformed the cohort by ~0.8 % mean PnL. Raising the gate should improve hit-rate without materially reducing trade frequency.",
    },
    {
        "key": "hold_horizon_hours",
        "old": 24, "new": 36,
        "rationale": "Median time-to-target across the last 10 mock trades on {symbol} was 31h. Extending the horizon to 36h captures more wins before forced evaluation.",
    },
    {
        "key": "max_position_size_pct",
        "old": 1.0, "new": 1.25,
        "rationale": "Sharpe ratio over the window (1.42) exceeds the goals target — modest size up is justified to convert edge to absolute return.",
    },
    {
        "key": "stop_loss_pct",
        "old": 1.5, "new": 1.2,
        "rationale": "Tightening the stop from 1.5 % to 1.2 % would have reduced max drawdown by ~1.8 % over the window with only a small drop in win-rate (61 → 58 %).",
    },
    {
        "key": "take_profit_pct",
        "old": 3.0, "new": 2.4,
        "rationale": "Most winning {signal} trades reversed before reaching the 3.0 % target. Tightening TP to 2.4 % locks in profit more reliably.",
    },
    {
        "key": "sentiment_weight",
        "old": 0.25, "new": 0.35,
        "rationale": "Sentiment signal correlated strongly with PnL outcomes ({symbol}: +0.42). Increasing the weight should improve overall accuracy.",
    },
]


def _drop_mock_proposal(symbol: str, signal: str) -> None:
    """Insert a plausible-looking parameter proposal so the Proposals tab populates."""
    import random
    from tradingagents.monitor import store, learning_config
    try:
        template = random.choice(_MOCK_PROPOSAL_TEMPLATES)
        params = learning_config.load_learned_params()
        new_params = dict(params)
        new_params[template["key"]] = template["new"]
        rationale = template["rationale"].format(signal=signal, symbol=symbol)
        store.record_params_proposal(
            params=new_params,
            diff={template["key"]: {"from": template["old"], "to": template["new"]}},
            rationale=f"[mock] {rationale}",
            applied=False,
        )
    except Exception as exc:
        logger.warning("mock-execute: could not record mock proposal: %s", exc)


def _fetch_broker_price(symbol: str, signal: str) -> Optional[float]:
    """Return the broker's current bid/ask price for the symbol (signal-aware)."""
    try:
        info = dashboard_manager.connector.get_symbol_info(symbol)
        if info:
            return float(info.ask if signal == "BUY" else info.bid)
    except Exception as exc:
        logger.debug("Broker price lookup failed for %s: %s", symbol, exc)
    return None


@app.post("/api/watchlist/{symbol}/mock-execute")
async def mock_execute_trade(symbol: str, signal: str = "BUY") -> Dict:
    """Skip LLM analysis and send a mock BUY/SELL signal through the full pipeline.

    Animates all 12 components over a random 20–30 s window in a background
    thread, fires the broker execution, records the decision, force-evaluates
    the outcome with real broker prices (so EXIT/PnL populate immediately),
    and drops a mock parameter proposal into the Proposals tab.
    """
    signal = signal.upper()
    if signal not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="signal must be BUY or SELL")
    entry = watchlist.get(symbol.upper())
    if not entry:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist. Add it first.")

    config = get_config()

    from tradingagents.monitor.live_progress import live_progress, COMPONENT_KEYS
    from tradingagents.monitor.scheduler import _maybe_execute_trade, simulate_mock_pipeline
    from tradingagents.monitor import store, learning_config
    import threading
    import random
    from datetime import datetime

    mock_text = (
        f"**Rating**: {signal}\n"
        f"**Confidence**: 0.90\n\n"
        f"Mock execution test — LLM analysis bypassed to exercise the broker execution path."
    )

    # All 12 components applicable so the full flow diagram lights up — never SKIPPED.
    run_id = live_progress.start_run(symbol.upper(), list(COMPONENT_KEYS))

    def _run_in_background() -> None:
        sym = symbol.upper()
        try:
            # Animate the full 12-stage pipeline for 20–30 seconds with variant content.
            simulate_mock_pipeline(run_id, signal, sym, mock_text)
            live_progress.set_stage(run_id, f"Mock {signal} — executing")

            result = _maybe_execute_trade(
                symbol=sym,
                decision_text=mock_text,
                signal=signal,
                decision_date=datetime.now().strftime("%Y-%m-%d"),
                config=config,
                execute_trade=True,
                allow_auto_trade_config=False,
            )

            watchlist.update_result(sym, mock_text, signal)

            execution_ok = result and result.get("status") in ("EXECUTED", "filled", "submitted")
            decision_id = None
            try:
                params = learning_config.load_learned_params()
                horizon = int(params.get("hold_horizon_hours", 24) or 24)
                decision_id = store.record_decision(
                    symbol=sym,
                    signal=signal,
                    decision_text=mock_text,
                    success=execution_ok,
                    horizon_hours=horizon,
                    error=None if execution_ok else (result or {}).get("reason") or (result or {}).get("message"),
                )

                # Force-populate outcome with real broker prices so the Decisions
                # ledger shows entry/exit/PnL immediately rather than "price unavailable".
                if decision_id:
                    entry_price = (result or {}).get("execution_price") or _fetch_broker_price(sym, signal)
                    exit_price = _fetch_broker_price(sym, "SELL" if signal == "BUY" else "BUY")
                    if entry_price and exit_price:
                        # Add a small ±0.3 % jitter to the exit so PnL is non-trivial in mock runs.
                        jitter = random.uniform(-0.003, 0.003)
                        exit_price = exit_price * (1.0 + jitter)
                        sign = 1.0 if signal == "BUY" else -1.0
                        pnl_pct = ((exit_price - entry_price) / entry_price) * sign * 100.0
                        store.save_outcome(
                            decision_id=decision_id,
                            entry_price=float(entry_price),
                            exit_price=float(exit_price),
                            pnl_pct=float(pnl_pct),
                            horizon_hours=horizon,
                            error=None,
                        )
                    elif entry_price:
                        store.save_outcome(
                            decision_id=decision_id,
                            entry_price=float(entry_price),
                            exit_price=None,
                            pnl_pct=None,
                            horizon_hours=horizon,
                        )
            except Exception as exc:
                logger.warning("mock-execute: could not record decision/outcome: %s", exc)

            # Drop a mock proposal so the Proposals tab has something to show.
            _drop_mock_proposal(sym, signal)

            live_progress.finish_run(run_id, "success", signal=signal)
        except Exception as exc:
            logger.error("mock-execute background thread failed: %s", exc, exc_info=True)
            live_progress.finish_run(run_id, "error", error=str(exc))

    threading.Thread(target=_run_in_background, daemon=True, name=f"mock-execute-{symbol}").start()

    return {"symbol": symbol.upper(), "signal": signal, "run_id": run_id}


@app.get("/api/analysis-flow")
async def get_analysis_flow(limit: int = 50, symbol: Optional[str] = None) -> List[Dict]:
    """Return recent decision flows with component-level traces when available.

    Filters out failed/timed-out analyses (success=false or has error).
    """
    from tradingagents.monitor import store

    flows = store.recent_analysis_flows(limit=limit * 2, symbol=symbol)  # Fetch extra to account for filtering
    successful_flows = [f for f in flows if f.get("success") and not f.get("error")][:limit]

    for flow in successful_flows:
        if flow.get("trace"):
            continue
        decision_text = flow.get("decision_text") or ""
        flow["trace"] = {
            "symbol": flow.get("symbol"),
            "signal": flow.get("signal"),
            "success": flow.get("success"),
            "timestamp": flow.get("decided_at"),
            "components": {
                "market_analyst": "",
                "sentiment_analyst": "",
                "news_analyst": "",
                "fundamentals_analyst": "",
                "bull_researcher": "",
                "bear_researcher": "",
                "research_manager": "",
                "trader": "",
                "aggressive_risk": "",
                "neutral_risk": "",
                "conservative_risk": "",
                "portfolio_manager": decision_text,
            },
            "debates": {
                "research": "",
                "risk": "",
            },
            "execution": None,
        }
        flow["trace_note"] = "Detailed component trace was not captured for this older decision."
    return successful_flows


@app.get("/api/analysis-flow/{decision_id}")
async def get_analysis_flow_detail(decision_id: int) -> Dict:
    """Return one saved component-level analysis trace."""
    from tradingagents.monitor import store

    trace = store.get_analysis_trace(decision_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"No trace found for decision {decision_id}")
    return trace


@app.get("/api/analysis-flow/{decision_id}/report")
async def get_analysis_flow_report(decision_id: int, format: str = "md"):
    """Render a management-ready report for one decision's analysis flow.

    Regenerates from the stored trace on demand so older runs work too. Returns
    Markdown as an attachment for download.
    """
    from fastapi.responses import Response
    from tradingagents.monitor import store
    from tradingagents.monitor.flow_report import render_flow_report

    trace = store.get_analysis_trace(decision_id)
    if not trace:
        # Legacy decisions predate component-trace capture — fall back to a
        # minimal trace built from the decision row so the report still renders.
        flow = next(
            (f for f in store.recent_analysis_flows(limit=500) if f.get("id") == decision_id),
            None,
        )
        if not flow:
            raise HTTPException(status_code=404, detail=f"No decision found for id {decision_id}")
        trace = {
            "symbol": flow.get("symbol", "?"),
            "signal": flow.get("signal", "?"),
            "success": flow.get("success", False),
            "timestamp": flow.get("decided_at", ""),
            "components": {"portfolio_manager": flow.get("decision_text") or ""},
            "debates": {"research": "", "risk": ""},
            "execution": None,
        }

    markdown = render_flow_report(
        trace,
        decision_id=decision_id,
        confidence=None,
        trading_mode=str(get_config().get("trading_mode", "")) or None,
    )
    symbol = str(trace.get("symbol", "flow")).upper()
    filename = f"flow_report_{symbol}_{decision_id}.md"
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/reports/summary")
async def get_reports_summary() -> Dict:
    """Return the rolling management summary (one row per decision)."""
    from tradingagents.monitor.flow_report import report_dir

    path = report_dir(get_config()) / "management_summary.md"
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"path": str(path), "content": content}


# ─── Token usage / Stop-Sonnet kill switch ──────────────────────────────────

@app.get("/api/token-usage")
async def get_token_usage() -> TokenUsage:
    """Current LLM token usage + kill-switch state."""
    return _build_token_usage(get_config())


@app.post("/api/token-usage/reset")
async def reset_token_usage() -> TokenUsage:
    """Zero the running token counter."""
    from tradingagents.monitor.token_usage import get_token_tracker
    get_token_tracker().reset()
    return _build_token_usage(get_config())


# ─── Market Intel ──────────────────────────────────────────────────────────

@app.get("/api/market-intel/categories")
async def list_market_intel_categories() -> List[Dict]:
    """Return the news categories the dashboard can pull (equities/macro/crypto/...)."""
    from tradingagents.dataflows.news_categories import list_categories
    return list_categories()


@app.get("/api/market-intel/snapshot")
async def get_market_intel_snapshot(
    look_back_days: int = 2,
    limit: int = 15,
    category: Optional[str] = None,
) -> Dict:
    """Cross-category market news + sentiment snapshot."""
    from tradingagents.dataflows.news_categories import get_market_intel_snapshot
    cats = [category] if category else None
    return get_market_intel_snapshot(
        look_back_days=look_back_days,
        limit=limit,
        categories=cats,
    )


# ─── Learning loop ─────────────────────────────────────────────────────────

from pydantic import BaseModel


class RejectProposalRequest(BaseModel):
    reason: Optional[str] = None


@app.get("/api/learning/scoreboard")
async def get_scoreboard(window_days: int = 30) -> Dict:
    """Win rate, mean PnL, sharpe, drawdown over the recent decision window."""
    from tradingagents.monitor import reviewer
    return reviewer.build_scoreboard(window_days=window_days).to_dict()


@app.get("/api/learning/decisions")
async def get_decisions(
    since: Optional[str] = None,
    limit: int = 100,
    symbol: Optional[str] = None,
) -> List[Dict]:
    """Decision ledger joined with outcomes. `since` is ISO-8601."""
    from datetime import datetime as _dt
    from tradingagents.monitor import store
    since_dt = None
    if since:
        try:
            since_dt = _dt.fromisoformat(since)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid `since`: {since}")
    rows = store.recent_decisions_with_outcomes(since=since_dt, limit=limit)
    if symbol:
        sym = symbol.upper()
        rows = [r for r in rows if (r.get("symbol") or "").upper() == sym]
    # Exclude failed/errored runs — only real BUY/SELL/HOLD decisions belong here.
    rows = [r for r in rows if r.get("signal") in {"BUY", "SELL", "HOLD"}]
    return rows


@app.post("/api/learning/evaluate-now")
async def evaluate_now() -> Dict:
    """Force-evaluate all pending decisions using current price as exit.

    Ignores the normal horizon check — useful in mock/test mode where you
    want to see PnL without waiting 24 h. Uses live market price as the
    exit price, so the result is 'unrealized PnL if closed now.'
    """
    from tradingagents.monitor import outcomes
    n = outcomes.evaluate_all_now()
    return {"evaluated": n}


@app.get("/api/learning/proposals")
async def get_proposals(status: str = "all", limit: int = 50) -> List[Dict]:
    """List proposals — status: pending|applied|rejected|all."""
    from tradingagents.monitor import store
    if status not in {"pending", "applied", "rejected", "all"}:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    return store.list_proposals(status=status, limit=limit)


@app.get("/api/learning/proposals/{proposal_id}")
async def get_proposal(proposal_id: int) -> Dict:
    """Full proposal row + matching markdown summary if findable on disk."""
    from tradingagents.monitor import store
    from tradingagents.monitor import reviewer

    proposal = store.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")

    # Best-effort: pick the .md whose mtime is closest to proposed_at.
    md_text: Optional[str] = None
    md_path: Optional[str] = None
    try:
        if reviewer.PROPOSALS_DIR.exists():
            from datetime import datetime as _dt
            proposed = _dt.fromisoformat(proposal["proposed_at"])
            candidates = sorted(reviewer.PROPOSALS_DIR.glob("*.md"))
            if candidates:
                def _delta(p):
                    return abs(_dt.fromtimestamp(p.stat().st_mtime) - proposed)
                best = min(candidates, key=_delta)
                if _delta(best).total_seconds() < 24 * 3600:
                    md_path = str(best)
                    md_text = best.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to attach proposal markdown: %s", e)

    return {**proposal, "markdown_path": md_path, "markdown": md_text}


@app.post("/api/learning/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: int) -> Dict:
    from tradingagents.monitor import store
    try:
        new_params = store.apply_proposal(proposal_id)
    except store.ProposalNotFound:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
    except store.ProposalAlreadyResolved as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"applied": True, "proposal_id": proposal_id, "params": new_params}


@app.post("/api/learning/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: int, body: RejectProposalRequest) -> Dict:
    from tradingagents.monitor import store
    try:
        proposal = store.reject_proposal(proposal_id, reason=body.reason)
    except store.ProposalNotFound:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
    except store.ProposalAlreadyResolved as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"rejected": True, "proposal_id": proposal_id, "proposal": proposal}


@app.get("/api/learning/params")
async def get_params() -> Dict:
    from tradingagents.monitor import learning_config
    return learning_config.load_learned_params()


@app.get("/api/learning/goals")
async def get_goals() -> Dict:
    from tradingagents.monitor import learning_config
    return learning_config.load_goals()


# --- App settings ----------------------------------------------------------

@app.get("/api/settings")
async def get_settings() -> Dict:
    from tradingagents.monitor import app_settings
    from tradingagents.llm_clients.ollama_models import list_ollama_models

    settings = app_settings.load_settings()
    return {
        "settings": settings,
        "ollama_models": list_ollama_models(),
        "settings_path": str(app_settings.settings_path()),
    }


@app.put("/api/settings")
async def update_settings(settings_patch: Dict) -> Dict:
    from tradingagents.monitor import app_settings
    from tradingagents.dataflows.config import set_config, get_config
    from tradingagents.llm_clients.ollama_models import list_ollama_models

    settings = app_settings.update_settings(settings_patch)
    set_config(settings)
    scheduler.set_config(get_config())
    scheduler.check_interval = int(settings.get("watchlist_check_interval_seconds", scheduler.check_interval))
    return {
        "settings": settings,
        "ollama_models": list_ollama_models(),
        "settings_path": str(app_settings.settings_path()),
    }


# ─── WebSocket ─────────────────────────────────────────────────────────────

@app.websocket("/ws/live-updates")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint — broadcasts status + watchlist updates."""
    await dashboard_manager.connect(websocket)
    last_event_count = 0

    try:
        while True:
            await asyncio.sleep(2)

            status = dashboard_manager.get_dashboard_status()
            wl = _get_enriched_watchlist()

            # Include any new analysis events since last push
            new_events = dashboard_manager._analysis_events[last_event_count:]
            last_event_count = len(dashboard_manager._analysis_events)

            message = {
                "type": "status_update",
                "data": status.model_dump(mode="json"),
                "watchlist": wl,
                "new_events": new_events,
            }

            await websocket.send_json(message)

    except WebSocketDisconnect:
        dashboard_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        dashboard_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
