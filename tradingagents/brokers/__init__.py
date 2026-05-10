"""
Brokers module for TradingAgents.

Provides integration with trading brokers like MetaTrader 5.
"""

from tradingagents.brokers.models import (
    OrderAction,
    OrderType,
    OrderStatus,
    MT5Order,
    AccountInfo,
    SymbolInfo,
    Position,
    ExecutionResult,
    PendingOrder,
    RiskLimits,
    ExecutionLog,
)
from tradingagents.brokers.mt5_connector import (
    MT5Connector,
    NativeMT5Connector,
    MockMT5Connector,
)
from tradingagents.brokers.order_generator import OrderGenerator
from tradingagents.brokers.risk_manager import RiskManager
from tradingagents.brokers.execution_engine import ExecutionEngine
from tradingagents.brokers.approval_cli import (
    display_pending_order,
    approve_pending_order_cli,
    show_execution_summary,
)

__all__ = [
    # Models
    "OrderAction",
    "OrderType",
    "OrderStatus",
    "MT5Order",
    "AccountInfo",
    "SymbolInfo",
    "Position",
    "ExecutionResult",
    "PendingOrder",
    "RiskLimits",
    "ExecutionLog",
    # Connectors
    "MT5Connector",
    "NativeMT5Connector",
    "MockMT5Connector",
    # Engines
    "OrderGenerator",
    "RiskManager",
    "ExecutionEngine",
    # CLI
    "display_pending_order",
    "approve_pending_order_cli",
    "show_execution_summary",
]
