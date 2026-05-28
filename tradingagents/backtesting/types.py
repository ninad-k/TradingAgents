from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class InstrumentKind(str, Enum):
    EQUITY = "EQUITY"
    FOREX = "FOREX"


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    kind: InstrumentKind
    point: float                 # price increment of one "point" (pip size for FX)
    pip_value_per_lot: float     # account-currency value of one point per 1.0 lot (FX only)
    min_volume: float
    max_volume: float
    volume_step: float
    spread_points: float         # typical spread expressed in points


@dataclass
class Bar:
    date: str                    # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class OrderIntent:
    side: str                    # "BUY" or "SELL"
    volume: float                # shares (equity) or lots (forex)
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    max_holding_hours: Optional[int] = None


@dataclass
class Trade:
    symbol: str
    side: str
    entry_date: str
    entry_price: float
    volume: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    max_holding_hours: Optional[int] = None
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    exit_reason: Optional[str] = None


@dataclass
class PortfolioValuePoint:
    date: str
    value: float


@dataclass
class PerformanceMetrics:
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    max_drawdown_date: Optional[str] = None
    total_return_pct: Optional[float] = None
    ending_value: Optional[float] = None


@dataclass
class BacktestConfig:
    ticker: str
    start_date: str
    end_date: str
    timeframe: str = "1d"
    cadence_bars: int = 5            # rebalance every N bars (weekly on daily bars)
    initial_capital: float = 100_000.0
    max_risk_percent: float = 2.0
    annual_trading_days: int = 252
    agent_config: dict = field(default_factory=dict)
    selected_analysts: tuple[str, ...] = ("market", "social", "news", "fundamentals")


@dataclass
class BacktestResult:
    config: BacktestConfig
    values: list[PortfolioValuePoint]
    trades: list[Trade]
    metrics: PerformanceMetrics
    benchmark_values: list[PortfolioValuePoint]


def position_pnl(spec: InstrumentSpec, side: str, entry_price: float,
                 exit_price: float, volume: float) -> float:
    """Account-currency PnL of closing a position. Sign by side."""
    direction = 1.0 if side == "BUY" else -1.0
    diff = (exit_price - entry_price) * direction
    if spec.kind == InstrumentKind.FOREX:
        return (diff / spec.point) * spec.pip_value_per_lot * volume
    return diff * volume
