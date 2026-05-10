"""FastAPI backend for trading dashboard."""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import asyncio
import json

from tradingagents.api.models import DashboardStatus, Trade, Position, AccountStatus
from tradingagents.brokers.analytics import ExecutionAnalytics
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

        metrics = self.analytics.get_performance_metrics()
        total_trades = len(self.analytics.executions)
        executed_trades = metrics['executions']
        win_rate = metrics['approval_rate']

        account = AccountStatus(
            trading_mode=trading_mode,
            account_balance=10000.0,
            account_equity=10000.0,
            available_margin=10000.0,
            total_pnl=0.0,
            total_pnl_percent=0.0,
            win_rate=win_rate,
            total_trades=total_trades,
            open_trades=0,
            closed_trades=executed_trades,
            largest_win=0.0,
            largest_loss=0.0,
            avg_trade_duration=0,
        )

        return DashboardStatus(
            timestamp=datetime.utcnow(),
            connected=True,
            account=account,
            open_positions=[],
            recent_trades=[],
            total_positions=0,
            total_closed_trades=executed_trades,
        )


dashboard_manager = DashboardManager()


def _on_analysis_event(event_type: str, data: Dict):
    """Scheduler callback — record event for next WebSocket broadcast."""
    dashboard_manager.record_analysis_event(event_type, data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the watchlist scheduler alongside the API."""
    config = get_config()

    # Wire scheduler event callback
    scheduler.set_event_callback(_on_analysis_event)
    scheduler.set_config(config)

    if config.get("watchlist_enabled", True):
        scheduler.start()
        logger.info("Watchlist scheduler started")

    logger.info("Trading Dashboard API started")
    yield

    scheduler.stop()
    logger.info("Trading Dashboard API stopped")


app = FastAPI(
    title="Trading Dashboard API",
    description="Real-time trading dashboard with TradingView watchlist monitoring",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS: allow only localhost React dev server
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
    trades = []
    for log in dashboard_manager.analytics.executions[-limit:]:
        if log.action == "executed":
            trades.append({
                "symbol": log.symbol,
                "action": log.action,
                "timestamp": log.timestamp.isoformat(),
                "details": log.details,
            })
    return trades


@app.get("/api/portfolio")
async def get_portfolio() -> Dict:
    metrics = dashboard_manager.analytics.get_performance_metrics()
    outcomes = dashboard_manager.analytics.get_decision_outcomes()
    return {
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


# ─── Watchlist ─────────────────────────────────────────────────────────────

@app.get("/api/watchlist")
async def get_watchlist() -> List[Dict]:
    """Get all monitored symbols with their latest signals."""
    entries = watchlist.to_dict_list()
    # Enrich with latest scheduler results
    results = scheduler.get_all_results()
    for entry in entries:
        sym = entry["symbol"]
        if sym in results:
            entry["latest_result"] = results[sym]
    return entries


@app.post("/api/watchlist/{symbol}")
async def add_to_watchlist(symbol: str, interval_hours: int = 4, include_news: bool = False) -> Dict:
    """Add a symbol to the watchlist."""
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
async def trigger_analysis(symbol: str) -> Dict:
    """Manually trigger an immediate analysis for a watchlist symbol."""
    entry = watchlist.get(symbol.upper())
    if not entry:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist. Add it first.")

    # Run in background thread to avoid blocking the API
    import threading
    def run():
        result = scheduler.trigger_now(symbol.upper())
        if result:
            dashboard_manager.record_analysis_event("analysis_complete", result.to_dict())

    threading.Thread(target=run, daemon=True).start()
    return {"triggered": True, "symbol": symbol.upper(), "message": "Analysis running in background"}


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
            wl = watchlist.to_dict_list()

            # Include any new analysis events since last push
            new_events = dashboard_manager._analysis_events[last_event_count:]
            last_event_count = len(dashboard_manager._analysis_events)

            message = {
                "type": "status_update",
                "data": status.model_dump(default=str),
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
