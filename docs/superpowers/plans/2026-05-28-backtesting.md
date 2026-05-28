# Backtesting Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backtester that runs the existing multi-agent ensemble over historical bars and reports portfolio performance (Sharpe, Sortino, max drawdown) for both equities (shares) and forex/XAUUSD (lots).

**Architecture:** New `tradingagents/backtesting/` package. A bar loop drives `TradingAgentsGraph.propagate(symbol, date)` at a configurable cadence, parses the Portfolio Manager's `PortfolioDecision` back from rendered markdown, turns it into an `OrderIntent` via a `PositionModel` (equities = shares; forex = the live `OrderGenerator`), and simulates fills/SL/TP against subsequent bars. A disk decision cache makes re-runs free; an as-of guard clamps the agents' data tools to the current bar date to prevent look-ahead. Equity is tracked with a unified PnL model (`equity = initial_capital + realized_pnl + unrealized_pnl`).

**Tech Stack:** Python, pandas, numpy, pydantic (existing `PortfolioDecision`), pytest. Reuses `tradingagents/dataflows` (yfinance/tradingview) and `tradingagents/brokers/order_generator.py`.

**v1 boundaries (explicit):** one instrument per run (multi-symbol shared portfolio is a future extension); leverage/margin not enforced (sizing is already risk-capped by `OrderGenerator`); as-of guard covers price + indicator tools (news/fundamentals as-of hardening is future work). The persona-agent confidence-signal pattern is out of scope.

---

## File Structure

| File | Responsibility |
|---|---|
| `tradingagents/backtesting/__init__.py` | Package exports + MIT attribution note |
| `tradingagents/backtesting/types.py` | Dataclasses/enums: `InstrumentKind`, `InstrumentSpec`, `Bar`, `OrderIntent`, `Trade`, `PortfolioValuePoint`, `PerformanceMetrics`, `BacktestConfig`, `BacktestResult`; `position_pnl()` helper |
| `tradingagents/backtesting/metrics.py` | `PerformanceMetricsCalculator` (Sharpe/Sortino/max-drawdown) — adapted from ai-hedge-fund |
| `tradingagents/backtesting/decision_cache.py` | `DecisionCache`: persist `(symbol, date)→PM markdown` keyed by config hash |
| `tradingagents/backtesting/portfolio.py` | `Portfolio`: unified PnL accounting, single open `Trade` |
| `tradingagents/backtesting/position_models.py` | `PositionModel` protocol, `EquitySharesModel`, `ForexLotModel` (wraps `OrderGenerator`) |
| `tradingagents/backtesting/data.py` | `BarProvider` protocol, `FakeBarProvider`, `YFinanceBarProvider`, `TradingViewBarProvider`, `INSTRUMENT_SPECS`, `get_spec()` |
| `tradingagents/backtesting/controller.py` | `BacktestController.decide()`: as-of guard + cache + `propagate` + `parse_pm_decision` |
| `tradingagents/backtesting/engine.py` | `BacktestEngine.run()`: bar loop, t+1 fills, intrabar SL/TP, mark-to-market |
| `tradingagents/backtesting/benchmarks.py` | `buy_and_hold()` equity curve |
| `tradingagents/backtesting/output.py` | `render_summary()` text report |
| `backtester.py` (repo root) | CLI entrypoint, mirrors `main.py` |
| `tradingagents/dataflows/config.py` | **modify**: add `apply_backtest_asof()` |
| `tradingagents/agents/utils/core_stock_tools.py` | **modify**: clamp `end_date` |
| `tradingagents/agents/utils/technical_indicators_tools.py` | **modify**: clamp `curr_date` |
| `tradingagents/agents/schemas.py` | **modify**: add `parse_pm_decision()` |
| `tests/backtesting/*` | tests per module |

---

## Task 1: Package skeleton + core types

**Files:**
- Create: `tradingagents/backtesting/__init__.py`
- Create: `tradingagents/backtesting/types.py`
- Test: `tests/backtesting/__init__.py`, `tests/backtesting/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_types.py
from tradingagents.backtesting.types import (
    InstrumentKind, InstrumentSpec, Bar, OrderIntent, Trade,
    PortfolioValuePoint, position_pnl,
)


def test_equity_pnl_long():
    spec = InstrumentSpec(symbol="AAPL", kind=InstrumentKind.EQUITY,
                          point=0.01, pip_value_per_lot=0.0,
                          min_volume=1, max_volume=1e9, volume_step=1,
                          spread_points=0.0)
    # 10 shares, +$5 move = +$50
    assert position_pnl(spec, "BUY", entry_price=100.0, exit_price=105.0, volume=10) == 50.0


def test_equity_pnl_short():
    spec = InstrumentSpec(symbol="AAPL", kind=InstrumentKind.EQUITY,
                          point=0.01, pip_value_per_lot=0.0,
                          min_volume=1, max_volume=1e9, volume_step=1,
                          spread_points=0.0)
    assert position_pnl(spec, "SELL", entry_price=100.0, exit_price=95.0, volume=10) == 50.0


def test_forex_pnl_long():
    # XAUUSD: point=0.01, pip_value_per_lot=1.0 -> pnl = (price_diff/point)*pip_value*volume
    spec = InstrumentSpec(symbol="XAUUSD", kind=InstrumentKind.FOREX,
                          point=0.01, pip_value_per_lot=1.0,
                          min_volume=0.01, max_volume=100, volume_step=0.01,
                          spread_points=30.0)
    # +1.00 move = 100 points * 1.0 * 1 lot = 100.0
    assert position_pnl(spec, "BUY", entry_price=2000.0, exit_price=2001.0, volume=1.0) == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError: tradingagents.backtesting`

- [ ] **Step 3: Create the package and types**

```python
# tradingagents/backtesting/__init__.py
"""Backtesting for the TradingAgents ensemble.

Structure and the metrics calculator are adapted from virattt/ai-hedge-fund
(`src/backtesting/`), MIT-licensed. See NOTICE in this package.
"""
```

```python
# tradingagents/backtesting/types.py
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
    selected_analysts: tuple = ("market", "social", "news", "fundamentals")


@dataclass
class BacktestResult:
    config: BacktestConfig
    values: list                 # list[PortfolioValuePoint]
    trades: list                 # list[Trade]
    metrics: PerformanceMetrics
    benchmark_values: list       # list[PortfolioValuePoint]


def position_pnl(spec: InstrumentSpec, side: str, entry_price: float,
                 exit_price: float, volume: float) -> float:
    """Account-currency PnL of closing a position. Sign by side."""
    direction = 1.0 if side == "BUY" else -1.0
    diff = (exit_price - entry_price) * direction
    if spec.kind == InstrumentKind.FOREX:
        return (diff / spec.point) * spec.pip_value_per_lot * volume
    return diff * volume
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_types.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/__init__.py tradingagents/backtesting/types.py tests/backtesting/__init__.py tests/backtesting/test_types.py
git commit -m "feat(backtesting): package skeleton and core types"
```

---

## Task 2: Performance metrics

**Files:**
- Create: `tradingagents/backtesting/metrics.py`
- Test: `tests/backtesting/test_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_metrics.py
from tradingagents.backtesting.types import PortfolioValuePoint
from tradingagents.backtesting.metrics import PerformanceMetricsCalculator


def _points(values):
    # synthetic consecutive daily dates
    dates = [f"2024-01-{i+1:02d}" for i in range(len(values))]
    return [PortfolioValuePoint(date=d, value=v) for d, v in zip(dates, values)]


def test_empty_returns_none_metrics():
    m = PerformanceMetricsCalculator().compute_metrics([])
    assert m.sharpe_ratio is None and m.max_drawdown is None


def test_monotonic_increase_has_no_drawdown():
    m = PerformanceMetricsCalculator().compute_metrics(_points([100, 101, 102, 103, 104]))
    assert m.max_drawdown == 0.0
    assert m.max_drawdown_date is None
    assert m.sharpe_ratio is not None


def test_drawdown_is_negative_percentage():
    # peak 110 then trough 99 -> drawdown = (99-110)/110 *100 = -10.0
    m = PerformanceMetricsCalculator().compute_metrics(_points([100, 110, 104, 99, 105]))
    assert round(m.max_drawdown, 4) == -10.0
    assert m.max_drawdown_date is not None


def test_total_return_and_ending_value():
    m = PerformanceMetricsCalculator().compute_metrics(_points([100, 110, 120]))
    assert m.ending_value == 120
    assert round(m.total_return_pct, 4) == 20.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError` for `metrics`

- [ ] **Step 3: Write the implementation (adapted from ai-hedge-fund, MIT)**

```python
# tradingagents/backtesting/metrics.py
from __future__ import annotations

from typing import Sequence

from .types import PerformanceMetrics, PortfolioValuePoint


class PerformanceMetricsCalculator:
    """Sharpe, Sortino, and max drawdown. Adapted from virattt/ai-hedge-fund (MIT)."""

    def __init__(self, *, annual_trading_days: int = 252, annual_rf_rate: float = 0.0434) -> None:
        self.annual_trading_days = annual_trading_days
        self.annual_rf_rate = annual_rf_rate

    def compute_metrics(self, values: Sequence[PortfolioValuePoint]) -> PerformanceMetrics:
        import numpy as np
        import pandas as pd

        if not values:
            return PerformanceMetrics()

        df = pd.DataFrame({"Date": [v.date for v in values],
                           "Portfolio Value": [v.value for v in values]})
        df = df.set_index("Date")
        ending_value = float(df["Portfolio Value"].iloc[-1])
        starting_value = float(df["Portfolio Value"].iloc[0])
        total_return_pct = ((ending_value - starting_value) / starting_value * 100.0
                            if starting_value else None)

        df["Daily Return"] = df["Portfolio Value"].pct_change()
        clean = df["Daily Return"].dropna()

        sharpe = sortino = None
        if len(clean) >= 2:
            daily_rf = self.annual_rf_rate / self.annual_trading_days
            excess = clean - daily_rf
            mean_excess = excess.mean()
            std_excess = excess.std()
            sharpe = (float(np.sqrt(self.annual_trading_days) * (mean_excess / std_excess))
                      if std_excess > 1e-12 else 0.0)
            downside = float(np.sqrt(np.mean(np.minimum(excess, 0) ** 2)))
            if downside > 1e-12:
                sortino = float(np.sqrt(self.annual_trading_days) * (mean_excess / downside))
            else:
                sortino = float("inf") if mean_excess > 0 else 0.0

        rolling_max = df["Portfolio Value"].cummax()
        drawdown = (df["Portfolio Value"] - rolling_max) / rolling_max
        min_dd = float(drawdown.min()) if len(drawdown) else 0.0
        max_drawdown = float(min_dd * 100.0)
        max_drawdown_date = drawdown.idxmin() if min_dd < 0 else None

        return PerformanceMetrics(
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_drawdown,
            max_drawdown_date=max_drawdown_date,
            total_return_pct=total_return_pct,
            ending_value=ending_value,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_metrics.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/metrics.py tests/backtesting/test_metrics.py
git commit -m "feat(backtesting): performance metrics calculator"
```

---

## Task 3: Look-ahead guard in the data tools

**Files:**
- Modify: `tradingagents/dataflows/config.py`
- Modify: `tradingagents/agents/utils/core_stock_tools.py`
- Modify: `tradingagents/agents/utils/technical_indicators_tools.py`
- Test: `tests/backtesting/test_asof_guard.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_asof_guard.py
import tradingagents.agents.utils.core_stock_tools as cst
import tradingagents.agents.utils.technical_indicators_tools as tit
from tradingagents.dataflows.config import set_config, apply_backtest_asof


def test_apply_backtest_asof_clamps_future_date():
    set_config({"backtest_as_of": "2024-03-01"})
    try:
        assert apply_backtest_asof("2024-12-31") == "2024-03-01"
        assert apply_backtest_asof("2024-01-15") == "2024-01-15"   # earlier untouched
    finally:
        set_config({"backtest_as_of": None})


def test_apply_backtest_asof_noop_when_unset():
    set_config({"backtest_as_of": None})
    assert apply_backtest_asof("2024-12-31") == "2024-12-31"


def test_get_stock_data_clamps_end_date(monkeypatch):
    captured = {}

    def fake_route(method, *args, **kwargs):
        captured["args"] = args
        return "ok"

    monkeypatch.setattr(cst, "route_to_vendor", fake_route)
    set_config({"backtest_as_of": "2024-03-01"})
    try:
        cst.get_stock_data.invoke({"symbol": "AAPL",
                                   "start_date": "2024-01-01",
                                   "end_date": "2024-12-31"})
    finally:
        set_config({"backtest_as_of": None})
    # args = (symbol, start_date, end_date)
    assert captured["args"][2] == "2024-03-01"


def test_get_indicators_clamps_curr_date(monkeypatch):
    captured = {}

    def fake_route(method, *args, **kwargs):
        captured["args"] = args
        return "ok"

    monkeypatch.setattr(tit, "route_to_vendor", fake_route)
    set_config({"backtest_as_of": "2024-03-01"})
    try:
        tit.get_indicators.invoke({"symbol": "AAPL", "indicator": "rsi",
                                   "curr_date": "2024-12-31", "look_back_days": 30})
    finally:
        set_config({"backtest_as_of": None})
    # args = (symbol, indicator, curr_date, look_back_days)
    assert captured["args"][2] == "2024-03-01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_asof_guard.py -v`
Expected: FAIL — `ImportError: cannot import name 'apply_backtest_asof'`

- [ ] **Step 3a: Add the helper to config.py**

Add to the end of `tradingagents/dataflows/config.py`:

```python
def apply_backtest_asof(date_str: str) -> str:
    """Clamp a tool's end/current date to the active backtest as-of date.

    During a backtest the controller sets ``backtest_as_of`` so the agents
    cannot read bars past the bar currently being decided. ISO dates compare
    lexicographically, so ``min`` is correct.
    """
    as_of = get_config().get("backtest_as_of")
    if as_of and date_str and date_str > as_of:
        return as_of
    return date_str
```

- [ ] **Step 3b: Clamp `end_date` in `get_stock_data`**

In `tradingagents/agents/utils/core_stock_tools.py`, add the import and clamp:

```python
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.config import apply_backtest_asof
```

Inside `get_stock_data`, replace the return line with:

```python
    end_date = apply_backtest_asof(end_date)
    return route_to_vendor("get_stock_data", symbol, start_date, end_date)
```

- [ ] **Step 3c: Clamp `curr_date` in `get_indicators`**

In `tradingagents/agents/utils/technical_indicators_tools.py`, add the import:

```python
from tradingagents.dataflows.config import apply_backtest_asof
```

Inside `get_indicators`, immediately after the docstring (before splitting indicators):

```python
    curr_date = apply_backtest_asof(curr_date)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_asof_guard.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/config.py tradingagents/agents/utils/core_stock_tools.py tradingagents/agents/utils/technical_indicators_tools.py tests/backtesting/test_asof_guard.py
git commit -m "feat(backtesting): as-of guard clamps data tools to bar date"
```

---

## Task 4: Parse PortfolioDecision back from markdown

**Files:**
- Modify: `tradingagents/agents/schemas.py`
- Test: `tests/backtesting/test_parse_pm_decision.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_parse_pm_decision.py
from tradingagents.agents.schemas import (
    PortfolioDecision, PortfolioRating, render_pm_decision, parse_pm_decision,
)


def test_roundtrip_full():
    original = PortfolioDecision(
        rating=PortfolioRating.BUY,
        executive_summary="Enter long, size 5%.",
        investment_thesis="Strong momentum and converging analysts.",
        price_target=2050.0,
        time_horizon="1 week",
        confidence=0.82,
    )
    parsed = parse_pm_decision(render_pm_decision(original))
    assert parsed.rating == PortfolioRating.BUY
    assert parsed.price_target == 2050.0
    assert parsed.time_horizon == "1 week"
    assert round(parsed.confidence, 2) == 0.82


def test_freetext_without_optionals_defaults_to_none():
    parsed = parse_pm_decision("The committee leans Sell here given the breakdown.")
    assert parsed.rating == PortfolioRating.SELL
    assert parsed.price_target is None
    assert parsed.time_horizon is None


def test_missing_rating_defaults_hold():
    parsed = parse_pm_decision("No clear edge in either direction.")
    assert parsed.rating == PortfolioRating.HOLD
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_parse_pm_decision.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_pm_decision'`

- [ ] **Step 3: Add `parse_pm_decision` to schemas.py**

Add these imports near the top of `tradingagents/agents/schemas.py`:

```python
import re
from tradingagents.agents.utils.rating import parse_rating
```

Add after `render_pm_decision`:

```python
def parse_pm_decision(markdown: str) -> PortfolioDecision:
    """Inverse of :func:`render_pm_decision`, tolerant of free-text fallback output.

    The rating is extracted with the shared 5-tier heuristic; optional numeric
    and text fields are best-effort regex matches that default to ``None``.
    """
    rating = PortfolioRating(parse_rating(markdown))

    def _grab(label: str):
        m = re.search(rf"\*\*{label}\*\*\s*[:\-]\s*(.+)", markdown, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _grab_float(label: str):
        raw = _grab(label)
        if not raw:
            return None
        m = re.search(r"-?\d+(?:\.\d+)?", raw)
        return float(m.group(0)) if m else None

    return PortfolioDecision(
        rating=rating,
        executive_summary=_grab("Executive Summary") or "",
        investment_thesis=_grab("Investment Thesis") or "",
        price_target=_grab_float("Price Target"),
        time_horizon=_grab("Time Horizon"),
        confidence=_grab_float("Confidence"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_parse_pm_decision.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/schemas.py tests/backtesting/test_parse_pm_decision.py
git commit -m "feat(backtesting): parse PortfolioDecision from rendered markdown"
```

---

## Task 5: Decision cache

**Files:**
- Create: `tradingagents/backtesting/decision_cache.py`
- Test: `tests/backtesting/test_decision_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_decision_cache.py
from tradingagents.backtesting.decision_cache import DecisionCache


def test_put_get_roundtrip(tmp_path):
    cache = DecisionCache(str(tmp_path), config_hash="abc123")
    assert cache.get("XAUUSD", "2024-03-01") is None
    cache.put("XAUUSD", "2024-03-01", "**Rating**: Buy")
    assert cache.get("XAUUSD", "2024-03-01") == "**Rating**: Buy"


def test_config_hash_isolates_entries(tmp_path):
    a = DecisionCache(str(tmp_path), config_hash="aaa")
    b = DecisionCache(str(tmp_path), config_hash="bbb")
    a.put("AAPL", "2024-03-01", "**Rating**: Buy")
    assert b.get("AAPL", "2024-03-01") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_decision_cache.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# tradingagents/backtesting/decision_cache.py
from __future__ import annotations

import os


class DecisionCache:
    """Persist Portfolio Manager markdown per (symbol, date), keyed by config hash."""

    def __init__(self, cache_dir: str, config_hash: str) -> None:
        self._dir = os.path.join(cache_dir, "backtest_decisions", config_hash)
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, symbol: str, date: str) -> str:
        safe = symbol.replace("/", "_").replace(":", "_")
        return os.path.join(self._dir, f"{safe}_{date}.md")

    def get(self, symbol: str, date: str):
        path = self._path(symbol, date)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def put(self, symbol: str, date: str, markdown: str) -> None:
        with open(self._path(symbol, date), "w", encoding="utf-8") as f:
            f.write(markdown)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_decision_cache.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/decision_cache.py tests/backtesting/test_decision_cache.py
git commit -m "feat(backtesting): disk decision cache keyed by config hash"
```

---

## Task 6: Portfolio (unified PnL accounting)

**Files:**
- Create: `tradingagents/backtesting/portfolio.py`
- Test: `tests/backtesting/test_portfolio.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_portfolio.py
from tradingagents.backtesting.types import InstrumentKind, InstrumentSpec
from tradingagents.backtesting.portfolio import Portfolio

EQ = InstrumentSpec("AAPL", InstrumentKind.EQUITY, 0.01, 0.0, 1, 1e9, 1, 0.0)


def test_starts_flat_at_initial_capital():
    p = Portfolio(initial_capital=10_000.0, spec=EQ)
    assert p.is_flat()
    assert p.equity(current_price=100.0) == 10_000.0


def test_open_then_unrealized_then_close_updates_equity():
    p = Portfolio(initial_capital=10_000.0, spec=EQ)
    p.open("BUY", date="2024-01-02", price=100.0, volume=10)
    assert not p.is_flat()
    assert p.equity(current_price=105.0) == 10_050.0   # +5 * 10 shares unrealized
    trade = p.close(date="2024-01-05", price=110.0, reason="TP")
    assert p.is_flat()
    assert trade.pnl == 100.0
    assert p.equity(current_price=110.0) == 10_100.0   # realized into equity
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_portfolio.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# tradingagents/backtesting/portfolio.py
from __future__ import annotations

from typing import Optional

from .types import InstrumentSpec, Trade, position_pnl


class Portfolio:
    """Single open position with PnL-based equity: initial + realized + unrealized."""

    def __init__(self, initial_capital: float, spec: InstrumentSpec) -> None:
        self.initial_capital = float(initial_capital)
        self.spec = spec
        self.realized_pnl = 0.0
        self.open_trade: Optional[Trade] = None

    def is_flat(self) -> bool:
        return self.open_trade is None

    def open(self, side: str, date: str, price: float, volume: float,
             stop_loss=None, take_profit=None, max_holding_hours=None) -> Trade:
        if self.open_trade is not None:
            raise RuntimeError("position already open")
        self.open_trade = Trade(
            symbol=self.spec.symbol, side=side, entry_date=date,
            entry_price=price, volume=volume, stop_loss=stop_loss,
            take_profit=take_profit, max_holding_hours=max_holding_hours,
        )
        return self.open_trade

    def unrealized(self, current_price: float) -> float:
        t = self.open_trade
        if t is None:
            return 0.0
        return position_pnl(self.spec, t.side, t.entry_price, current_price, t.volume)

    def equity(self, current_price: float) -> float:
        return self.initial_capital + self.realized_pnl + self.unrealized(current_price)

    def close(self, date: str, price: float, reason: str) -> Trade:
        t = self.open_trade
        if t is None:
            raise RuntimeError("no open position")
        t.exit_date = date
        t.exit_price = price
        t.exit_reason = reason
        t.pnl = position_pnl(self.spec, t.side, t.entry_price, price, t.volume)
        self.realized_pnl += t.pnl
        self.open_trade = None
        return t
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_portfolio.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/portfolio.py tests/backtesting/test_portfolio.py
git commit -m "feat(backtesting): PnL-based portfolio with single open position"
```

---

## Task 7: Position models

**Files:**
- Create: `tradingagents/backtesting/position_models.py`
- Test: `tests/backtesting/test_position_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_position_models.py
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.backtesting.types import Bar, InstrumentKind, InstrumentSpec
from tradingagents.backtesting.position_models import EquitySharesModel, ForexLotModel

EQ = InstrumentSpec("AAPL", InstrumentKind.EQUITY, 0.01, 0.0, 1, 1e9, 1, 0.0)
FX = InstrumentSpec("XAUUSD", InstrumentKind.FOREX, 0.01, 1.0, 0.01, 100, 0.01, 30.0)
BAR = Bar(date="2024-03-01", open=100.0, high=101.0, low=99.0, close=100.0)


def _decision(rating, price_target=None):
    return PortfolioDecision(rating=rating, executive_summary="x",
                             investment_thesis="x", price_target=price_target)


def test_equity_hold_returns_none():
    assert EquitySharesModel().build_order(_decision(PortfolioRating.HOLD), EQ, BAR, 10_000.0) is None


def test_equity_buy_sizes_by_equity_fraction():
    intent = EquitySharesModel(buy_fraction=0.05).build_order(
        _decision(PortfolioRating.BUY, price_target=120.0), EQ, BAR, 10_000.0)
    assert intent.side == "BUY"
    # 5% of 10k = $500 / $100 close = 5 shares
    assert intent.volume == 5
    assert intent.take_profit == 120.0


def test_forex_buy_uses_order_generator_lots_and_levels():
    intent = ForexLotModel(max_risk_percent=2.0).build_order(
        _decision(PortfolioRating.BUY, price_target=2050.0), FX, Bar(
            date="2024-03-01", open=2000.0, high=2010.0, low=1990.0, close=2000.0), 10_000.0)
    assert intent.side == "BUY"
    assert intent.volume > 0
    assert intent.stop_loss is not None and intent.stop_loss < 2000.0   # SL below entry for long
    assert intent.take_profit == 2050.0


def test_forex_hold_returns_none():
    assert ForexLotModel().build_order(_decision(PortfolioRating.HOLD), FX, BAR, 10_000.0) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_position_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# tradingagents/backtesting/position_models.py
from __future__ import annotations

from typing import Optional, Protocol

from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.brokers.models import AccountInfo, OrderAction, SymbolInfo
from tradingagents.brokers.order_generator import OrderGenerator

from .types import Bar, InstrumentKind, InstrumentSpec, OrderIntent

_BUY_RATINGS = {PortfolioRating.BUY, PortfolioRating.OVERWEIGHT}
_SELL_RATINGS = {PortfolioRating.SELL, PortfolioRating.UNDERWEIGHT}


class PositionModel(Protocol):
    def build_order(self, decision: PortfolioDecision, spec: InstrumentSpec,
                    bar: Bar, equity: float) -> Optional[OrderIntent]:
        ...


class EquitySharesModel:
    """Share-based sizing as a fraction of current equity."""

    def __init__(self, buy_fraction: float = 0.05, reduce_fraction: float = 0.03) -> None:
        self.buy_fraction = buy_fraction
        self.reduce_fraction = reduce_fraction

    def build_order(self, decision, spec, bar, equity) -> Optional[OrderIntent]:
        if decision.rating in _BUY_RATINGS:
            side = "BUY"
        elif decision.rating in _SELL_RATINGS:
            side = "SELL"
        else:
            return None
        frac = self.buy_fraction if decision.rating in (PortfolioRating.BUY, PortfolioRating.SELL) else self.reduce_fraction
        notional = equity * frac
        volume = int(notional / bar.close) if bar.close > 0 else 0
        if volume <= 0:
            return None
        return OrderIntent(side=side, volume=float(volume), entry_price=bar.close,
                           stop_loss=None, take_profit=decision.price_target)


class ForexLotModel:
    """Wraps the live OrderGenerator so the backtest exercises deploy sizing/SL/TP."""

    def __init__(self, max_risk_percent: float = 2.0) -> None:
        self._gen = OrderGenerator(max_risk_percent=max_risk_percent)

    def _symbol_info(self, spec: InstrumentSpec, bar: Bar) -> SymbolInfo:
        spread_price = spec.spread_points * spec.point
        return SymbolInfo(
            symbol=spec.symbol, bid=bar.close, ask=bar.close + spread_price,
            spread=spec.spread_points, digits=2, point=spec.point,
            min_volume=spec.min_volume, max_volume=spec.max_volume,
            volume_step=spec.volume_step,
        )

    def _account_info(self, equity: float) -> AccountInfo:
        return AccountInfo(
            login=0, server="backtest", account_type="DEMO", currency="USD",
            balance=equity, equity=equity, free_margin=equity, margin_level=1000.0,
        )

    def build_order(self, decision, spec, bar, equity) -> Optional[OrderIntent]:
        order = self._gen.decision_to_order(
            decision=decision, symbol=spec.symbol,
            symbol_info=self._symbol_info(spec, bar),
            account_info=self._account_info(equity),
            decision_id=f"bt:{spec.symbol}:{bar.date}",
        )
        if order is None:
            return None
        side = "BUY" if order.action == OrderAction.BUY else "SELL"
        entry = order.entry_price or (bar.close + spec.spread_points * spec.point
                                      if side == "BUY" else bar.close)
        return OrderIntent(side=side, volume=order.volume, entry_price=entry,
                           stop_loss=order.stop_loss, take_profit=order.take_profit,
                           max_holding_hours=order.max_holding_time_hours)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_position_models.py -v`
Expected: PASS (4 tests)

> Note: if `test_forex_buy_uses_order_generator_lots_and_levels` fails on the SL assertion, read `OrderGenerator._get_stop_loss` — it computes SL from spread/point. Adjust the `FX` spec's `spread_points`/`point` in the test to produce a stop at least 20 points away (the generator's floor), do not weaken the assertion.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/position_models.py tests/backtesting/test_position_models.py
git commit -m "feat(backtesting): equity and forex position models"
```

---

## Task 8: Bar providers + instrument specs

**Files:**
- Create: `tradingagents/backtesting/data.py`
- Test: `tests/backtesting/test_data.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_data.py
from tradingagents.backtesting.types import Bar, InstrumentKind
from tradingagents.backtesting.data import FakeBarProvider, get_spec


def test_get_spec_known_forex_is_forex():
    spec = get_spec("XAUUSD")
    assert spec.kind == InstrumentKind.FOREX
    assert spec.point > 0


def test_get_spec_unknown_defaults_to_equity():
    spec = get_spec("AAPL")
    assert spec.kind == InstrumentKind.EQUITY


def test_fake_provider_filters_and_sorts_by_date():
    bars = [Bar("2024-01-03", 3, 3, 3, 3), Bar("2024-01-01", 1, 1, 1, 1),
            Bar("2024-01-02", 2, 2, 2, 2)]
    provider = FakeBarProvider({"AAPL": bars})
    out = provider.get_bars("AAPL", "2024-01-01", "2024-01-02", "1d")
    assert [b.date for b in out] == ["2024-01-01", "2024-01-02"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_data.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# tradingagents/backtesting/data.py
from __future__ import annotations

from typing import Dict, List, Protocol

from .types import Bar, InstrumentKind, InstrumentSpec

# Forex/commodity specs. point = pip size; pip_value_per_lot = account-USD value
# of one point per 1.0 lot. Extend by adding rows.
_FOREX_SPECS: Dict[str, InstrumentSpec] = {
    "XAUUSD": InstrumentSpec("XAUUSD", InstrumentKind.FOREX, 0.01, 1.0, 0.01, 100, 0.01, 30.0),
    "EURUSD": InstrumentSpec("EURUSD", InstrumentKind.FOREX, 0.0001, 10.0, 0.01, 100, 0.01, 1.5),
    "GBPUSD": InstrumentSpec("GBPUSD", InstrumentKind.FOREX, 0.0001, 10.0, 0.01, 100, 0.01, 2.0),
    "USDJPY": InstrumentSpec("USDJPY", InstrumentKind.FOREX, 0.01, 6.7, 0.01, 100, 0.01, 1.5),
}

INSTRUMENT_SPECS = _FOREX_SPECS


def get_spec(symbol: str) -> InstrumentSpec:
    """Return the spec for a symbol; unknown symbols are treated as equities (shares)."""
    if symbol.upper() in _FOREX_SPECS:
        return _FOREX_SPECS[symbol.upper()]
    return InstrumentSpec(symbol, InstrumentKind.EQUITY, 0.01, 0.0, 1, 1e9, 1, 0.0)


class BarProvider(Protocol):
    def get_bars(self, symbol: str, start: str, end: str, timeframe: str) -> List[Bar]:
        ...


class FakeBarProvider:
    """In-memory provider for tests."""

    def __init__(self, bars_by_symbol: Dict[str, List[Bar]]) -> None:
        self._bars = bars_by_symbol

    def get_bars(self, symbol, start, end, timeframe) -> List[Bar]:
        bars = sorted(self._bars.get(symbol, []), key=lambda b: b.date)
        return [b for b in bars if start <= b.date <= end]


class YFinanceBarProvider:
    """Daily equity bars via yfinance (timeframe '1d')."""

    def get_bars(self, symbol, start, end, timeframe) -> List[Bar]:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(start=start, end=end)
        out = []
        for ts, row in hist.iterrows():
            out.append(Bar(date=ts.strftime("%Y-%m-%d"), open=float(row["Open"]),
                           high=float(row["High"]), low=float(row["Low"]),
                           close=float(row["Close"]), volume=float(row.get("Volume", 0.0))))
        return out


class TradingViewBarProvider:
    """Forex/commodity bars via tvdatafeed (TradingView)."""

    _INTERVALS = {"1d": "in_daily", "1h": "in_1_hour", "4h": "in_4_hour"}

    def get_bars(self, symbol, start, end, timeframe) -> List[Bar]:
        from tvDatafeed import Interval, TvDatafeed
        from tradingagents.dataflows.tradingview import TV_EXCHANGE_MAP
        tv = TvDatafeed()
        interval = getattr(Interval, self._INTERVALS.get(timeframe, "in_daily"))
        exchange = TV_EXCHANGE_MAP.get(symbol.upper(), "OANDA")
        df = tv.get_hist(symbol=symbol, exchange=exchange, interval=interval, n_bars=5000)
        out = []
        for ts, row in df.iterrows():
            date = ts.strftime("%Y-%m-%d")
            if start <= date <= end:
                out.append(Bar(date=date, open=float(row["open"]), high=float(row["high"]),
                               low=float(row["low"]), close=float(row["close"]),
                               volume=float(row.get("volume", 0.0))))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_data.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/data.py tests/backtesting/test_data.py
git commit -m "feat(backtesting): bar providers and instrument specs"
```

---

## Task 9: Controller (agent bridge)

**Files:**
- Create: `tradingagents/backtesting/controller.py`
- Test: `tests/backtesting/test_controller.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_controller.py
from tradingagents.agents.schemas import PortfolioRating
from tradingagents.backtesting.controller import BacktestController
from tradingagents.backtesting.decision_cache import DecisionCache
from tradingagents.dataflows.config import get_config


class FakeGraph:
    def __init__(self):
        self.calls = []

    def propagate(self, symbol, date):
        # record the as-of value visible to the agents at decision time
        self.calls.append((symbol, date, get_config().get("backtest_as_of")))
        final_state = {"final_trade_decision": "**Rating**: Buy\n\n**Price Target**: 2050"}
        return final_state, "Buy"


def test_decide_parses_and_caches(tmp_path):
    graph = FakeGraph()
    cache = DecisionCache(str(tmp_path), "h1")
    ctrl = BacktestController(graph=graph, cache=cache)

    d1 = ctrl.decide("XAUUSD", "2024-03-01")
    assert d1.rating == PortfolioRating.BUY
    assert d1.price_target == 2050.0
    assert graph.calls[0][2] == "2024-03-01"        # as-of set during propagate
    assert get_config().get("backtest_as_of") is None   # reset afterwards

    # second call hits cache -> no new propagate
    ctrl.decide("XAUUSD", "2024-03-01")
    assert len(graph.calls) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_controller.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# tradingagents/backtesting/controller.py
from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, parse_pm_decision
from tradingagents.dataflows.config import set_config

from .decision_cache import DecisionCache


class BacktestController:
    """Bridge: run the agent ensemble for one bar, with as-of guard and caching."""

    def __init__(self, graph, cache: DecisionCache) -> None:
        self._graph = graph
        self._cache = cache

    def decide(self, symbol: str, date: str) -> PortfolioDecision:
        cached = self._cache.get(symbol, date)
        if cached is not None:
            return parse_pm_decision(cached)

        set_config({"backtest_as_of": date})
        try:
            final_state, _ = self._graph.propagate(symbol, date)
            markdown = final_state["final_trade_decision"]
        finally:
            set_config({"backtest_as_of": None})

        self._cache.put(symbol, date, markdown)
        return parse_pm_decision(markdown)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_controller.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/controller.py tests/backtesting/test_controller.py
git commit -m "feat(backtesting): controller bridges ensemble with as-of and cache"
```

---

## Task 10: Engine (bar loop + fill simulation)

**Files:**
- Create: `tradingagents/backtesting/engine.py`
- Test: `tests/backtesting/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_engine.py
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.backtesting.types import Bar, BacktestConfig, InstrumentKind, InstrumentSpec
from tradingagents.backtesting.data import FakeBarProvider
from tradingagents.backtesting.position_models import EquitySharesModel
from tradingagents.backtesting.engine import BacktestEngine

EQ = InstrumentSpec("AAPL", InstrumentKind.EQUITY, 0.01, 0.0, 1, 1e9, 1, 0.0)


class StubController:
    """Returns a fixed decision on the first bar only, Hold thereafter."""

    def __init__(self, first_decision):
        self._first = first_decision
        self._seen = set()

    def decide(self, symbol, date):
        if date in self._seen:
            return PortfolioDecision(rating=PortfolioRating.HOLD, executive_summary="",
                                     investment_thesis="")
        self._seen.add(date)
        return self._first


def _bars():
    # rising then a bar that taps the take-profit
    return [
        Bar("2024-01-01", 100, 100, 100, 100),
        Bar("2024-01-02", 100, 101, 100, 100),   # entry fills at this open (t+1 = 100)
        Bar("2024-01-03", 101, 106, 101, 105),   # high 106 >= TP 105 -> exit
        Bar("2024-01-04", 105, 105, 105, 105),
    ]


def test_buy_then_take_profit_exit():
    provider = FakeBarProvider({"AAPL": _bars()})
    decision = PortfolioDecision(rating=PortfolioRating.BUY, executive_summary="",
                                 investment_thesis="", price_target=105.0)
    config = BacktestConfig(ticker="AAPL", start_date="2024-01-01", end_date="2024-01-04",
                            cadence_bars=1, initial_capital=10_000.0)
    engine = BacktestEngine(config=config, spec=EQ, provider=provider,
                            controller=StubController(decision),
                            position_model=EquitySharesModel(buy_fraction=0.05))
    result = engine.run()

    assert len(result.trades) == 1
    t = result.trades[0]
    assert t.side == "BUY"
    assert t.entry_price == 100.0           # t+1 open
    assert t.exit_reason == "TP"
    assert t.exit_price == 105.0            # tapped intrabar at TP
    # equity curve has one point per bar and ends above initial
    assert len(result.values) == len(_bars())
    assert result.values[-1].value > 10_000.0


def test_sl_first_when_bar_hits_both():
    # long with SL=98 and TP=110; a bar with low 97 and high 111 must exit at SL
    bars = [
        Bar("2024-01-01", 100, 100, 100, 100),
        Bar("2024-01-02", 100, 100, 100, 100),   # entry at open 100
        Bar("2024-01-03", 100, 111, 97, 100),    # both hit -> SL first
    ]
    provider = FakeBarProvider({"AAPL": bars})

    class SLController:
        def decide(self, symbol, date):
            if date == "2024-01-01":
                return PortfolioDecision(rating=PortfolioRating.BUY, executive_summary="",
                                         investment_thesis="")
            return PortfolioDecision(rating=PortfolioRating.HOLD, executive_summary="",
                                     investment_thesis="")

    class FixedSLModel:
        def build_order(self, decision, spec, bar, equity):
            from tradingagents.backtesting.types import OrderIntent
            if decision.rating == PortfolioRating.BUY:
                return OrderIntent(side="BUY", volume=10, entry_price=bar.close,
                                   stop_loss=98.0, take_profit=110.0)
            return None

    config = BacktestConfig(ticker="AAPL", start_date="2024-01-01", end_date="2024-01-03",
                            cadence_bars=1, initial_capital=10_000.0)
    engine = BacktestEngine(config=config, spec=EQ, provider=provider,
                            controller=SLController(), position_model=FixedSLModel())
    result = engine.run()
    assert result.trades[0].exit_reason == "SL"
    assert result.trades[0].exit_price == 98.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# tradingagents/backtesting/engine.py
from __future__ import annotations

from typing import List, Optional

from .benchmarks import buy_and_hold
from .metrics import PerformanceMetricsCalculator
from .portfolio import Portfolio
from .types import (
    Bar, BacktestConfig, BacktestResult, InstrumentSpec, OrderIntent,
    PortfolioValuePoint, Trade,
)


class BacktestEngine:
    """Single-instrument bar loop. Entries fill at the next bar's open; SL/TP are
    checked intrabar (SL takes priority when a bar hits both)."""

    def __init__(self, config: BacktestConfig, spec: InstrumentSpec,
                 provider, controller, position_model) -> None:
        self.config = config
        self.spec = spec
        self.provider = provider
        self.controller = controller
        self.position_model = position_model

    def _hours_to_bars(self, hours: Optional[int]) -> Optional[int]:
        if not hours:
            return None
        if self.config.timeframe == "1d":
            return max(1, hours // 24)
        if self.config.timeframe == "1h":
            return max(1, hours)
        if self.config.timeframe == "4h":
            return max(1, hours // 4)
        return None

    def _check_exit(self, trade: Trade, bar: Bar, bars_held: int) -> Optional[tuple]:
        """Return (exit_price, reason) if the bar triggers an exit, else None."""
        long = trade.side == "BUY"
        # SL first (worst case) when both could trigger in one bar.
        if trade.stop_loss is not None:
            if long and bar.low <= trade.stop_loss:
                return (min(bar.open, trade.stop_loss), "SL")
            if not long and bar.high >= trade.stop_loss:
                return (max(bar.open, trade.stop_loss), "SL")
        if trade.take_profit is not None:
            if long and bar.high >= trade.take_profit:
                return (max(bar.open, trade.take_profit), "TP")
            if not long and bar.low <= trade.take_profit:
                return (min(bar.open, trade.take_profit), "TP")
        max_bars = self._hours_to_bars(trade.max_holding_hours)
        if max_bars is not None and bars_held >= max_bars:
            return (bar.close, "TIME")
        return None

    def run(self) -> BacktestResult:
        bars: List[Bar] = self.provider.get_bars(
            self.config.ticker, self.config.start_date, self.config.end_date,
            self.config.timeframe)
        portfolio = Portfolio(self.config.initial_capital, self.spec)
        values: List[PortfolioValuePoint] = []
        trades: List[Trade] = []
        pending: Optional[OrderIntent] = None
        bars_held = 0

        for i, bar in enumerate(bars):
            # 1) Fill a pending entry at this bar's open.
            if pending is not None and portfolio.is_flat():
                portfolio.open(side=pending.side, date=bar.date, price=bar.open,
                               volume=pending.volume, stop_loss=pending.stop_loss,
                               take_profit=pending.take_profit,
                               max_holding_hours=pending.max_holding_hours)
                bars_held = 0
                pending = None

            # 2) Manage an open position (SL/TP/time exits) using this bar's range.
            if not portfolio.is_flat():
                bars_held += 1
                exit_ = self._check_exit(portfolio.open_trade, bar, bars_held)
                if exit_ is not None:
                    trades.append(portfolio.close(date=bar.date, price=exit_[0], reason=exit_[1]))

            # 3) On a rebalance bar while flat, ask the ensemble and schedule entry.
            if portfolio.is_flat() and pending is None and i % self.config.cadence_bars == 0:
                decision = self.controller.decide(self.config.ticker, bar.date)
                equity_now = portfolio.equity(bar.close)
                pending = self.position_model.build_order(decision, self.spec, bar, equity_now)

            values.append(PortfolioValuePoint(date=bar.date, value=portfolio.equity(bar.close)))

        # Force-close any open position at the last bar's close.
        if not portfolio.is_flat() and bars:
            trades.append(portfolio.close(date=bars[-1].date, price=bars[-1].close, reason="EOD"))
            values[-1] = PortfolioValuePoint(date=bars[-1].date,
                                             value=portfolio.equity(bars[-1].close))

        metrics = PerformanceMetricsCalculator(
            annual_trading_days=self.config.annual_trading_days).compute_metrics(values)
        benchmark = buy_and_hold(bars, self.config.initial_capital, self.spec)
        return BacktestResult(config=self.config, values=values, trades=trades,
                              metrics=metrics, benchmark_values=benchmark)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_engine.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/engine.py tests/backtesting/test_engine.py
git commit -m "feat(backtesting): bar-loop engine with t+1 fills and SL/TP exits"
```

---

## Task 11: Benchmark (buy & hold)

**Files:**
- Create: `tradingagents/backtesting/benchmarks.py`
- Test: `tests/backtesting/test_benchmarks.py`

> Note: Task 10's `engine.py` imports `buy_and_hold` from this module. If implementing strictly in order, create a minimal `benchmarks.py` stub before running Task 10's tests, or implement this task first. The TDD steps below define the real behavior.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_benchmarks.py
from tradingagents.backtesting.types import Bar, InstrumentKind, InstrumentSpec
from tradingagents.backtesting.benchmarks import buy_and_hold

EQ = InstrumentSpec("AAPL", InstrumentKind.EQUITY, 0.01, 0.0, 1, 1e9, 1, 0.0)


def test_buy_and_hold_tracks_price_change():
    bars = [Bar("2024-01-01", 100, 100, 100, 100),
            Bar("2024-01-02", 100, 100, 100, 110)]
    out = buy_and_hold(bars, initial_capital=10_000.0, spec=EQ)
    assert out[0].value == 10_000.0
    # bought at first close 100; +10% -> 11,000
    assert round(out[1].value, 2) == 11_000.0


def test_buy_and_hold_empty():
    assert buy_and_hold([], 10_000.0, EQ) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_benchmarks.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# tradingagents/backtesting/benchmarks.py
from __future__ import annotations

from typing import List

from .types import Bar, InstrumentSpec, PortfolioValuePoint, position_pnl


def buy_and_hold(bars: List[Bar], initial_capital: float,
                 spec: InstrumentSpec) -> List[PortfolioValuePoint]:
    """Equity curve of buying at the first bar's close and holding."""
    if not bars:
        return []
    entry = bars[0].close
    volume = initial_capital / entry if entry else 0.0
    out = []
    for bar in bars:
        pnl = position_pnl(spec, "BUY", entry, bar.close, volume)
        out.append(PortfolioValuePoint(date=bar.date, value=initial_capital + pnl))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_benchmarks.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/benchmarks.py tests/backtesting/test_benchmarks.py
git commit -m "feat(backtesting): buy-and-hold benchmark"
```

---

## Task 12: Output rendering

**Files:**
- Create: `tradingagents/backtesting/output.py`
- Test: `tests/backtesting/test_output.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_output.py
from tradingagents.backtesting.types import (
    BacktestConfig, BacktestResult, PerformanceMetrics, PortfolioValuePoint, Trade,
)
from tradingagents.backtesting.output import render_summary


def test_render_summary_contains_key_numbers():
    config = BacktestConfig(ticker="XAUUSD", start_date="2024-01-01", end_date="2024-02-01")
    metrics = PerformanceMetrics(sharpe_ratio=1.23, sortino_ratio=2.0,
                                 max_drawdown=-5.5, total_return_pct=12.0,
                                 ending_value=112_000.0)
    result = BacktestResult(config=config,
                            values=[PortfolioValuePoint("2024-01-01", 100_000.0)],
                            trades=[Trade("XAUUSD", "BUY", "2024-01-02", 2000.0, 1.0,
                                          exit_date="2024-01-09", exit_price=2050.0, pnl=5000.0,
                                          exit_reason="TP")],
                            metrics=metrics, benchmark_values=[])
    text = render_summary(result)
    assert "XAUUSD" in text
    assert "Sharpe" in text and "1.23" in text
    assert "Trades: 1" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_output.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# tradingagents/backtesting/output.py
from __future__ import annotations

from .types import BacktestResult


def _fmt(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def render_summary(result: BacktestResult) -> str:
    c, m = result.config, result.metrics
    wins = sum(1 for t in result.trades if (t.pnl or 0) > 0)
    lines = [
        f"Backtest: {c.ticker}  {c.start_date} -> {c.end_date}  ({c.timeframe}, cadence={c.cadence_bars})",
        f"Initial capital: {c.initial_capital:,.2f}",
        f"Ending value:    {_fmt(m.ending_value)}",
        f"Total return:    {_fmt(m.total_return_pct)}%",
        f"Sharpe:          {_fmt(m.sharpe_ratio)}",
        f"Sortino:         {_fmt(m.sortino_ratio)}",
        f"Max drawdown:    {_fmt(m.max_drawdown)}%  ({m.max_drawdown_date or 'n/a'})",
        f"Trades: {len(result.trades)}  (wins: {wins})",
    ]
    if result.benchmark_values:
        bench = result.benchmark_values[-1].value
        lines.append(f"Buy & hold end:  {bench:,.2f}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_output.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/output.py tests/backtesting/test_output.py
git commit -m "feat(backtesting): text summary rendering"
```

---

## Task 13: CLI entrypoint + package wiring

**Files:**
- Create: `backtester.py` (repo root)
- Modify: `tradingagents/backtesting/__init__.py`
- Test: `tests/backtesting/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_cli.py
from backtester import build_config_hash, parse_args


def test_parse_args_defaults():
    ns = parse_args(["--ticker", "XAUUSD", "--start", "2024-01-01", "--end", "2024-03-01"])
    assert ns.ticker == "XAUUSD"
    assert ns.cadence == 5
    assert ns.timeframe == "1d"
    assert ns.initial_capital == 100_000.0


def test_config_hash_is_stable_and_sensitive():
    base = {"llm_provider": "ollama", "deep_think_llm": "qwen3.6:latest"}
    assert build_config_hash(base) == build_config_hash(dict(base))
    assert build_config_hash(base) != build_config_hash({**base, "deep_think_llm": "gpt-5.4"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/backtesting/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtester'`

- [ ] **Step 3a: Write the CLI**

```python
# backtester.py
"""CLI: backtest the TradingAgents ensemble over a historical window.

Example:
    python backtester.py --ticker XAUUSD --start 2024-01-01 --end 2024-03-01 --cadence 5
"""
from __future__ import annotations

import argparse
import hashlib
import json

from dotenv import load_dotenv

from tradingagents.backtesting.controller import BacktestController
from tradingagents.backtesting.data import (
    TradingViewBarProvider, YFinanceBarProvider, get_spec,
)
from tradingagents.backtesting.decision_cache import DecisionCache
from tradingagents.backtesting.engine import BacktestEngine
from tradingagents.backtesting.output import render_summary
from tradingagents.backtesting.position_models import EquitySharesModel, ForexLotModel
from tradingagents.backtesting.types import BacktestConfig, InstrumentKind
from tradingagents.default_config import DEFAULT_CONFIG


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Backtest the TradingAgents ensemble.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--start", required=True, dest="start")
    p.add_argument("--end", required=True, dest="end")
    p.add_argument("--timeframe", default="1d", choices=["1d", "1h", "4h"])
    p.add_argument("--cadence", type=int, default=5, help="rebalance every N bars")
    p.add_argument("--initial-capital", type=float, default=100_000.0, dest="initial_capital")
    p.add_argument("--max-risk-percent", type=float, default=2.0, dest="max_risk_percent")
    return p.parse_args(argv)


def build_config_hash(agent_config: dict) -> str:
    keys = ("llm_provider", "deep_think_llm", "quick_think_llm",
            "max_debate_rounds", "max_risk_discuss_rounds")
    payload = {k: agent_config.get(k) for k in keys}
    blob = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def main(argv=None):
    load_dotenv()
    ns = parse_args(argv)

    spec = get_spec(ns.ticker)
    agent_config = DEFAULT_CONFIG.copy()
    config_hash = build_config_hash(agent_config)

    config = BacktestConfig(
        ticker=ns.ticker, start_date=ns.start, end_date=ns.end,
        timeframe=ns.timeframe, cadence_bars=ns.cadence,
        initial_capital=ns.initial_capital, max_risk_percent=ns.max_risk_percent,
        agent_config=agent_config,
    )

    # Lazy import so unit tests (which never call main) don't construct LLM clients.
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    graph = TradingAgentsGraph(selected_analysts=list(config.selected_analysts),
                               config=agent_config)

    provider = (TradingViewBarProvider() if spec.kind == InstrumentKind.FOREX
                else YFinanceBarProvider())
    position_model = (ForexLotModel(max_risk_percent=ns.max_risk_percent)
                      if spec.kind == InstrumentKind.FOREX
                      else EquitySharesModel())
    cache = DecisionCache(agent_config["data_cache_dir"], config_hash)
    controller = BacktestController(graph=graph, cache=cache)

    engine = BacktestEngine(config=config, spec=spec, provider=provider,
                            controller=controller, position_model=position_model)
    result = engine.run()
    print(render_summary(result))
    return result


if __name__ == "__main__":
    main()
```

- [ ] **Step 3b: Export the public API from the package**

Append to `tradingagents/backtesting/__init__.py`:

```python
from .types import BacktestConfig, BacktestResult          # noqa: E402
from .engine import BacktestEngine                          # noqa: E402
from .controller import BacktestController                  # noqa: E402
from .data import get_spec                                  # noqa: E402

__all__ = ["BacktestConfig", "BacktestResult", "BacktestEngine",
           "BacktestController", "get_spec"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/backtesting/test_cli.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backtester.py tradingagents/backtesting/__init__.py tests/backtesting/test_cli.py
git commit -m "feat(backtesting): CLI entrypoint and package exports"
```

---

## Task 14: Full-suite check, attribution NOTICE, manual smoke test

**Files:**
- Create: `tradingagents/backtesting/NOTICE`

- [ ] **Step 1: Run the whole backtesting suite**

Run: `pytest tests/backtesting/ -v`
Expected: PASS — all tests across tasks 1-13 green.

- [ ] **Step 2: Add the attribution NOTICE**

```text
# tradingagents/backtesting/NOTICE
Portions of this package (metrics.py, and the structure of engine.py,
portfolio.py, benchmarks.py, output.py) are adapted from
virattt/ai-hedge-fund (https://github.com/virattt/ai-hedge-fund),
licensed under the MIT License.
```

- [ ] **Step 3: Manual smoke test (equities, real LLM + yfinance)**

Run a short, cheap window so the LLM cost is small:
```bash
python backtester.py --ticker AAPL --start 2024-01-01 --end 2024-02-01 --cadence 5
```
Expected: prints a summary block with Sharpe/Sortino/Max drawdown/Trades; a second run is much faster (decision cache hits). Verify `~/.tradingagents/cache/backtest_decisions/<hash>/` contains `AAPL_*.md` files.

- [ ] **Step 4: Manual smoke test (forex, TradingView)**

Requires `tvdatafeed` installed and network. Confirm forex path end-to-end:
```bash
python backtester.py --ticker XAUUSD --start 2024-01-01 --end 2024-02-01 --cadence 5
```
Expected: summary prints; trades (if any) show lot-sized volumes and SL/TP levels from `OrderGenerator`. If `tvdatafeed` is missing, install it (`pip install tvdatafeed`) — do not silently skip the forex path.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtesting/NOTICE
git commit -m "docs(backtesting): MIT attribution NOTICE for adapted code"
```

---

## Self-Review notes (addressed)

- **Spec coverage:** types→T1; metrics→T2; as-of guard→T3; decision parse→T4; cache→T5; portfolio→T6; position models (OrderGenerator reuse)→T7; data/specs→T8; controller→T9; engine fills/SL-TP→T10; benchmarks→T11; output→T12; CLI→T13; attribution + smoke→T14.
- **Forward-reference fix:** `engine.py` (T10) imports `buy_and_hold` from `benchmarks.py` (T11); the note in T11 says to stub it first or reorder. When using subagent-driven execution, implement T11 before T10 or create the stub.
- **Type consistency:** `PositionModel.build_order(decision, spec, bar, equity)` signature is identical in the protocol (T7), both models (T7), the engine call site (T10), and all test stubs. `BacktestResult` fields used in `output.py` (T12) match `types.py` (T1). `controller.decide` returns `PortfolioDecision`; engine consumes `.rating`/`.price_target` via the position model only.
- **No placeholders:** every code step is complete and runnable.
