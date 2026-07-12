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
    # --- Transaction cost model (Qlib Exchange-style; all default to 0.0 so a
    # spec constructed without them is cost-free, preserving legacy behaviour) ---
    commission_rate: float = 0.0     # EQUITY: commission as a fraction of notional (price*volume), per fill
    commission_per_lot: float = 0.0  # FOREX: commission in account currency per 1.0 lot, per fill
    min_commission: float = 0.0      # floor on commission per fill (account currency)
    slippage_points: float = 0.0     # adverse fill movement in points, applied per fill


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
    pnl: Optional[float] = None              # NET realized PnL (gross minus round-trip cost)
    exit_reason: Optional[str] = None
    gross_pnl: Optional[float] = None        # PnL before transaction costs
    entry_cost: float = 0.0                  # commission paid on entry fill
    cost: float = 0.0                        # total round-trip cost (entry + exit commission)


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
    profit_factor: Optional[float] = None
    expectancy: Optional[float] = None
    win_rate: Optional[float] = None
    trade_count: int = 0
    total_cost: float = 0.0
    acceptance_passed: bool = False
    acceptance_reasons: list[str] = field(default_factory=list)


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


def trade_cost(spec: InstrumentSpec, price: float, volume: float) -> float:
    """Account-currency commission for ONE fill (entry or exit).

    Mirrors Qlib's ``Exchange`` open/close cost split: equities are charged a
    rate on notional, forex a flat amount per lot, both floored by
    ``min_commission``. A spec with no cost fields returns 0.0.
    """
    if volume <= 0:
        return 0.0
    if spec.kind == InstrumentKind.FOREX:
        commission = spec.commission_per_lot * volume
    else:
        commission = spec.commission_rate * price * volume
    if commission <= 0.0 and spec.min_commission <= 0.0:
        return 0.0
    return max(spec.min_commission, commission)


def apply_slippage(spec: InstrumentSpec, market_action: str, price: float) -> float:
    """Adverse-fill adjustment for a market order.

    ``market_action`` is the actual side executed in the market ("BUY" or
    "SELL"): a market buy fills higher, a market sell fills lower. Returns the
    input price unchanged when ``slippage_points`` is 0.
    """
    slip = spec.slippage_points * spec.point
    if slip <= 0.0:
        return price
    return price + slip if market_action == "BUY" else price - slip
