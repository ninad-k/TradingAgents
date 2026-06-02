"""FastAPI backend for trading dashboard."""

import logging
import os
from typing import List, Dict, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import asyncio
import json

from tradingagents.api.models import (
    DashboardStatus, Trade, Position, AccountStatus, TradeDirection, TradeStatus
)
from tradingagents.brokers.analytics import ExecutionAnalytics
from tradingagents.brokers.mt5_connector import get_shared_mt5_connector
from tradingagents.brokers.models import OrderAction
from tradingagents.dataflows.config import get_config
from tradingagents.monitor.watchlist import watchlist
from tradingagents.monitor.scheduler import scheduler

logger = logging.getLogger(__name__)


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

    logger.info("Trading Dashboard API started")
    yield

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
        interval_hours = 0 if interval_minutes <= 1 else max(1, round(interval_minutes / 60))
    entry = watchlist.add(symbol.upper(), interval_hours, include_news)
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
    return rows


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
