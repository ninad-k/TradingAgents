"""
Pydantic models for MT5 integration.

These models represent trading orders, execution results, and MT5 account information
in a broker-agnostic way.
"""

from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class OrderAction(str, Enum):
    """Order direction."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "PENDING"          # Waiting for user approval
    APPROVED = "APPROVED"        # User approved, ready to execute
    EXECUTING = "EXECUTING"      # Being placed on broker
    EXECUTED = "EXECUTED"        # Successfully placed on MT5
    REJECTED = "REJECTED"        # User or system rejected
    FAILED = "FAILED"            # Execution failed
    CLOSED = "CLOSED"            # Position closed


class MT5Order(BaseModel):
    """Order to be placed on MT5."""

    symbol: str = Field(description="Symbol to trade (e.g., EURUSD, AAPL, BTCUSD)")
    action: OrderAction = Field(description="BUY or SELL")
    volume: float = Field(description="Volume/lot size to trade")
    order_type: OrderType = Field(default=OrderType.MARKET, description="Order type")

    # Price levels
    entry_price: Optional[float] = Field(default=None, description="Entry price (for limit orders)")
    stop_loss: Optional[float] = Field(default=None, description="Stop loss price")
    take_profit: Optional[float] = Field(default=None, description="Take profit price")

    # Risk management
    trailing_stop_distance: Optional[float] = Field(default=None, description="Trailing stop distance in pips")
    max_holding_time_hours: Optional[int] = Field(default=None, description="Maximum holding time in hours")
    max_loss_per_trade: Optional[float] = Field(default=None, description="Max loss per trade in USD")

    # Reference & metadata
    decision_id: str = Field(description="Unique ID of the TradingAgents decision")
    reason: str = Field(description="Executive summary from TradingAgents decision")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Optional comment
    comment: Optional[str] = Field(default=None, description="Optional order comment")


class AccountInfo(BaseModel):
    """MT5 Account information."""

    login: int = Field(description="Account number")
    server: str = Field(description="Broker server name")
    account_type: str = Field(description="Account type: REAL or DEMO")
    currency: str = Field(description="Account currency")

    # Balance & equity
    balance: float = Field(description="Account balance")
    equity: float = Field(description="Current equity")
    free_margin: float = Field(description="Free margin available")
    margin_level: float = Field(description="Margin level percentage")

    # Risk metrics
    daily_pl: Optional[float] = Field(default=None, description="Daily profit/loss")
    max_drawdown: Optional[float] = Field(default=None, description="Maximum drawdown")
    open_positions: int = Field(default=0, description="Number of open positions")


class SymbolInfo(BaseModel):
    """MT5 Symbol information."""

    symbol: str = Field(description="Symbol name")
    bid: float = Field(description="Current bid price")
    ask: float = Field(description="Current ask price")
    spread: float = Field(description="Bid-ask spread in pips")

    # Contract specs
    digits: int = Field(description="Number of decimal places")
    point: float = Field(description="Point value (0.0001 for most FX)")
    min_volume: float = Field(description="Minimum volume")
    max_volume: float = Field(description="Maximum volume")
    volume_step: float = Field(description="Volume step")

    # Account-currency value of a one-`point` price move per 1.0 lot. Drives
    # risk-based sizing. None when unknown — sizing must refuse rather than guess.
    pip_value_per_lot: Optional[float] = Field(
        default=None,
        description="Account-currency value of a one-point move per 1.0 lot",
    )

    # Swaps & fees
    swap_long: Optional[float] = Field(default=None, description="Long swap per lot")
    swap_short: Optional[float] = Field(default=None, description="Short swap per lot")

    # Trading hours
    trade_mode: Optional[str] = Field(default=None, description="Trade mode (e.g., FULL, CLOSEONLY)")


class Position(BaseModel):
    """Open position on MT5."""

    ticket: int = Field(description="Position ticket number")
    symbol: str = Field(description="Symbol")
    type: OrderAction = Field(description="Position type: BUY or SELL")

    volume: float = Field(description="Position volume")
    entry_price: float = Field(description="Entry price")
    current_price: float = Field(description="Current price")

    # P&L
    profit: float = Field(description="Current profit/loss in currency")
    profit_percent: float = Field(description="Current profit/loss percentage")

    # Risk management
    stop_loss: Optional[float] = Field(default=None, description="Stop loss price")
    take_profit: Optional[float] = Field(default=None, description="Take profit price")

    # Metadata
    open_time: datetime = Field(description="Position open time")
    open_comment: Optional[str] = Field(default=None, description="Opening comment")
    decision_id: Optional[str] = Field(default=None, description="Linked TradingAgents decision ID")


class ExecutionResult(BaseModel):
    """Result of order execution."""

    decision_id: str = Field(description="Original TradingAgents decision ID")
    order: MT5Order = Field(description="The order that was executed")

    # Execution details
    status: OrderStatus = Field(description="Current execution status")
    ticket: Optional[int] = Field(default=None, description="MT5 ticket number if executed")

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = Field(default=None)
    executed_at: Optional[datetime] = Field(default=None)

    # Result details
    execution_price: Optional[float] = Field(default=None, description="Actual execution price")
    message: Optional[str] = Field(default=None, description="Status message or error")

    # Risk metrics at execution
    account_balance_at_execution: Optional[float] = Field(default=None)
    margin_level_at_execution: Optional[float] = Field(default=None)


class PendingOrder(BaseModel):
    """Order waiting for user approval."""

    pending_id: str = Field(description="Unique ID for this pending approval")
    order: MT5Order = Field(description="The order details")
    account_info: AccountInfo = Field(description="Account state at time of proposal")
    symbol_info: SymbolInfo = Field(description="Symbol info at time of proposal")

    # Risk analysis
    risk_per_trade: float = Field(description="Dollar risk per this trade")
    reward_target: Optional[float] = Field(default=None, description="Dollar reward target (to TP)")
    risk_reward_ratio: Optional[float] = Field(default=None, description="Risk/Reward ratio (e.g., 1:2)")

    # Justification
    decision_reasoning: str = Field(description="Full reasoning from TradingAgents")
    risk_check_message: Optional[str] = Field(default=None, description="Result of risk manager checks")

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(default=None, description="When approval expires")


class RiskLimits(BaseModel):
    """Risk management limits."""

    max_daily_loss: Optional[float] = Field(default=None, description="Max daily loss in USD")
    max_drawdown: Optional[float] = Field(default=None, description="Max drawdown in USD")
    max_open_positions: Optional[int] = Field(default=5, description="Max number of open positions")
    max_position_size: Optional[float] = Field(default=None, description="Max position size in lots")
    trailing_stop_distance: Optional[float] = Field(default=None, description="Default trailing stop in pips")

    # Risk per trade
    max_risk_per_trade_percent: Optional[float] = Field(default=2.0, description="Max % of account to risk per trade")
    max_risk_per_trade_usd: Optional[float] = Field(default=None, description="Max USD to risk per trade")

    # Position management
    close_expired_positions: bool = Field(default=True, description="Auto-close positions after time_horizon")
    update_trailing_stops: bool = Field(default=True, description="Auto-update trailing stops")


class ExecutionLog(BaseModel):
    """Log entry for an execution."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    decision_id: str = Field(description="TradingAgents decision ID")
    action: str = Field(description="Action taken (proposed, approved, rejected, executed, closed, etc.)")
    symbol: str = Field(description="Symbol")
    details: Dict[str, Any] = Field(description="Additional details")

    # Linking
    ticket: Optional[int] = Field(default=None, description="MT5 ticket if applicable")
    parent_log_id: Optional[str] = Field(default=None, description="Parent log entry ID for sequences")
