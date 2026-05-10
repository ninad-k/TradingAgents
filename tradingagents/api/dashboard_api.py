"""FastAPI backend for trading dashboard."""

import logging
from typing import List, Dict
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json

from tradingagents.api.models import DashboardStatus, Trade, Position, AccountStatus
from tradingagents.brokers.analytics import ExecutionAnalytics
from tradingagents.dataflows.config import get_config

logger = logging.getLogger(__name__)


class DashboardManager:
    """Manages dashboard data and WebSocket connections."""

    def __init__(self):
        """Initialize dashboard manager."""
        self.analytics = ExecutionAnalytics()
        self.connections: List[WebSocket] = []
        self.last_trade_count = 0

    async def connect(self, websocket: WebSocket):
        """Register WebSocket connection."""
        await websocket.accept()
        self.connections.append(websocket)
        logger.info(f"Client connected. Total clients: {len(self.connections)}")

    def disconnect(self, websocket: WebSocket):
        """Unregister WebSocket connection."""
        self.connections.remove(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.connections)}")

    async def broadcast(self, message: Dict):
        """Broadcast message to all connected clients."""
        if not self.connections:
            return

        message_json = json.dumps(message, default=str)
        for connection in self.connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")

    def get_dashboard_status(self) -> DashboardStatus:
        """Get current dashboard status."""
        config = get_config()
        trading_mode = config.get("trading_mode", "paper")

        # Get metrics from analytics
        metrics = self.analytics.get_performance_metrics()
        outcomes = self.analytics.get_decision_outcomes()

        # Calculate account metrics
        total_trades = len(self.analytics.executions)
        executed_trades = metrics['executions']
        win_rate = metrics['approval_rate']

        # Create account status
        account = AccountStatus(
            trading_mode=trading_mode,
            account_balance=10000.0,  # Default demo balance
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

        # Create dashboard status
        status = DashboardStatus(
            timestamp=datetime.utcnow(),
            connected=True,
            account=account,
            open_positions=[],
            recent_trades=[],
            total_positions=0,
            total_closed_trades=executed_trades,
        )

        return status


# Global dashboard manager
dashboard_manager = DashboardManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifespan."""
    logger.info("Trading Dashboard API started")
    yield
    logger.info("Trading Dashboard API stopped")


# Create FastAPI app
app = FastAPI(
    title="Trading Dashboard API",
    description="Real-time trading dashboard backend",
    version="0.1.0",
    lifespan=lifespan,
)

# Disable CORS for security (localhost only)
# app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/status")
async def get_status() -> DashboardStatus:
    """Get current dashboard status."""
    return dashboard_manager.get_dashboard_status()


@app.get("/api/trades")
async def get_trades(limit: int = 50) -> List[Dict]:
    """Get recent trades."""
    trades = []

    for log in dashboard_manager.analytics.executions[-limit:]:
        if log.action == "executed":
            trade = {
                "symbol": log.symbol,
                "action": log.action,
                "timestamp": log.timestamp.isoformat(),
                "details": log.details,
            }
            trades.append(trade)

    return trades


@app.get("/api/portfolio")
async def get_portfolio() -> Dict:
    """Get portfolio summary."""
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
    """Get detailed analytics."""
    metrics = dashboard_manager.analytics.get_performance_metrics()
    outcomes = dashboard_manager.analytics.get_decision_outcomes()

    return {
        "metrics": metrics,
        "outcomes": outcomes,
        "total_actions": metrics['total_actions'],
        "approval_rate": f"{metrics['approval_rate']:.1f}%",
    }


@app.websocket("/ws/live-updates")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await dashboard_manager.connect(websocket)

    try:
        while True:
            # Send status update every 2 seconds
            await asyncio.sleep(2)

            status = dashboard_manager.get_dashboard_status()
            message = {
                "type": "status_update",
                "data": status.model_dump(default=str),
            }

            await websocket.send_json(message)

    except WebSocketDisconnect:
        dashboard_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        dashboard_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
