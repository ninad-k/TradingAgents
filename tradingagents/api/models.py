"""Data models for dashboard API."""

from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum


class TradeStatus(str, Enum):
    """Trade status options."""
    OPEN = "open"
    CLOSED = "closed"
    REJECTED = "rejected"
    FAILED = "failed"


class TradeDirection(str, Enum):
    """Trade direction."""
    LONG = "long"
    SHORT = "short"


class Trade(BaseModel):
    """Trade record model."""
    symbol: str
    entry_price: float
    entry_time: datetime
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    quantity: float
    direction: TradeDirection
    status: TradeStatus
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    duration_seconds: Optional[int] = None
    reason: Optional[str] = None
    comment: Optional[str] = None


class Position(BaseModel):
    """Open position model."""
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    direction: TradeDirection
    unrealized_pnl: float
    unrealized_pnl_percent: float
    entry_time: datetime
    duration_seconds: int
    comment: Optional[str] = None


class AccountStatus(BaseModel):
    """Account status model."""
    trading_mode: str
    server: Optional[str] = None
    account_balance: float
    account_equity: float
    available_margin: float
    total_pnl: float
    total_pnl_percent: float
    win_rate: float
    total_trades: int
    open_trades: int
    closed_trades: int
    largest_win: float
    largest_loss: float
    avg_trade_duration: int


class TokenUsage(BaseModel):
    """LLM token usage + kill-switch state for the dashboard."""
    tokens_in: int = 0
    tokens_out: int = 0
    total: int = 0
    llm_calls: int = 0
    budget_max: int = 0          # 0 = unlimited
    llm_enabled: bool = True     # "Stop Sonnet" state


class DashboardStatus(BaseModel):
    """Overall dashboard status."""
    timestamp: datetime
    connected: bool
    account: AccountStatus
    open_positions: List[Position]
    recent_trades: List[Trade]
    total_positions: int
    total_closed_trades: int
    token_usage: Optional[TokenUsage] = None


class TradeEvent(BaseModel):
    """Event for real-time updates."""
    type: str  # "trade", "position", "status", "error"
    symbol: Optional[str] = None
    timestamp: datetime
    data: Dict
