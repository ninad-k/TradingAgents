"""Tests for BacktestEngine: bar-loop fills, SL/TP exits, and EOD close."""
from __future__ import annotations

import pytest

from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.backtesting.benchmarks import buy_and_hold
from tradingagents.backtesting.data import FakeBarProvider, get_spec
from tradingagents.backtesting.engine import BacktestEngine
from tradingagents.backtesting.position_models import EquitySharesModel
from tradingagents.backtesting.types import Bar, BacktestConfig

EQ = get_spec("AAPL")


# ---------------------------------------------------------------------------
# Stub controller
# ---------------------------------------------------------------------------

class _StubController:
    """Returns a pre-canned decision for every call."""

    def __init__(self, decision: PortfolioDecision) -> None:
        self._decision = decision

    def decide(self, symbol: str, date: str) -> PortfolioDecision:
        return self._decision


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _equity_spec():
    return get_spec("AAPL")


def _buy_decision(tp: float) -> PortfolioDecision:
    return PortfolioDecision(
        rating=PortfolioRating.BUY,
        executive_summary="buy",
        investment_thesis="long",
        price_target=tp,
    )


def _buy_decision_sl_tp(sl: float, tp: float) -> PortfolioDecision:
    # EquitySharesModel ignores stop_loss from decision; we will need to
    # monkey-patch the OrderIntent after build_order, or override the model.
    # Instead, use a custom position model that includes a stop_loss.
    return PortfolioDecision(
        rating=PortfolioRating.BUY,
        executive_summary="buy",
        investment_thesis="long",
        price_target=tp,
    )


class _EquitySharesModelWithSL(EquitySharesModel):
    """Variant that also sets stop_loss on the OrderIntent."""

    def __init__(self, buy_fraction: float, stop_loss: float) -> None:
        super().__init__(buy_fraction=buy_fraction)
        self._sl = stop_loss

    def build_order(self, decision, spec, bar, equity):
        intent = super().build_order(decision, spec, bar, equity)
        if intent is not None:
            from dataclasses import replace
            intent = replace(intent, stop_loss=self._sl)
        return intent


# ---------------------------------------------------------------------------
# Test 1: BUY → entry next open → TP hit
# ---------------------------------------------------------------------------

def test_buy_then_take_profit_exit():
    """
    Trace (cadence_bars=1):
      bar0 (i=0): flat + cadence → decide BUY, TP=105.
                  EquitySharesModel(0.05): 5% of 10000 / close 100 = 5 shares → pending.
      bar1 (i=1): fill at open 100 (entry_price=100).
                  manage: high 101 < 105 → no exit. equity = 10000 + (101-100)*5 = 10005.
      bar2 (i=2): manage: high 106 >= TP 105 → exit at max(open 101, 105)=105 reason "TP".
                  equity = 10000 + (105-100)*5 = 10025.
      bar3 (i=3): flat, cadence → decide again (no pending because already exited / same
                  bar logic; position is flat so another BUY could be queued). No open
                  position at end so no EOD close needed.
    Expect: 1 completed trade, entry 100, exit 105, reason "TP".
            values length == 4, final value > 10000.
    """
    bars = [
        Bar("2024-01-01", open=99,  high=100, low=98,  close=100, volume=1000),
        Bar("2024-01-02", open=100, high=101, low=99,  close=101, volume=1000),
        Bar("2024-01-03", open=101, high=106, low=100, close=105, volume=1000),
        Bar("2024-01-04", open=105, high=106, low=104, close=105, volume=1000),
    ]
    spec = _equity_spec()
    provider = FakeBarProvider({"AAPL": bars})
    config = BacktestConfig(
        ticker="AAPL",
        start_date="2024-01-01",
        end_date="2024-01-04",
        cadence_bars=1,
        initial_capital=10_000.0,
    )
    controller = _StubController(_buy_decision(tp=105.0))
    position_model = EquitySharesModel(buy_fraction=0.05)

    engine = BacktestEngine(
        config=config,
        provider=provider,
        spec=spec,
        controller=controller,
        position_model=position_model,
    )
    result = engine.run()

    # One trade should have been completed (TP hit on bar2)
    completed = [t for t in result.trades if t.exit_price is not None]
    assert len(completed) >= 1, f"Expected at least 1 completed trade, got {result.trades}"

    tp_trade = next((t for t in completed if t.exit_reason == "TP"), None)
    assert tp_trade is not None, f"No TP trade found: {completed}"
    assert tp_trade.entry_price == 100.0
    assert tp_trade.exit_price == 105.0
    assert tp_trade.exit_reason == "TP"

    # equity curve has one point per bar
    assert len(result.values) == 4

    # portfolio grew
    assert result.values[-1].value > 10_000.0

    # benchmark present
    assert len(result.benchmark_values) == 4


# ---------------------------------------------------------------------------
# Test 2: SL fires before TP when bar hits both
# ---------------------------------------------------------------------------

def test_sl_first_when_bar_hits_both():
    """
    BUY with SL=98, TP=110.
      bar0 (i=0): flat + cadence → decide BUY → pending, entry_price≈100, SL=98, TP=110.
      bar1 (i=1): fill at open 100.
                  manage: low 101 >= SL 98, high 101 < TP 110 → no exit.
      bar2 (i=2): manage: low 97 < SL 98 → SL branch first.
                  exit at min(open 100, SL 98) = 98, reason "SL".
    Expect: exit_reason == "SL", exit_price == 98.
    """
    bars = [
        Bar("2024-01-01", open=99,  high=100, low=98,  close=100, volume=1000),
        Bar("2024-01-02", open=100, high=101, low=101, close=101, volume=1000),
        Bar("2024-01-03", open=100, high=111, low=97,  close=100, volume=1000),
    ]
    spec = _equity_spec()
    provider = FakeBarProvider({"AAPL": bars})
    config = BacktestConfig(
        ticker="AAPL",
        start_date="2024-01-01",
        end_date="2024-01-03",
        cadence_bars=1,
        initial_capital=10_000.0,
    )
    controller = _StubController(_buy_decision_sl_tp(sl=98.0, tp=110.0))
    position_model = _EquitySharesModelWithSL(buy_fraction=0.05, stop_loss=98.0)

    engine = BacktestEngine(
        config=config,
        provider=provider,
        spec=spec,
        controller=controller,
        position_model=position_model,
    )
    result = engine.run()

    completed = [t for t in result.trades if t.exit_price is not None]
    assert len(completed) >= 1, f"No completed trades: {result.trades}"

    sl_trade = next((t for t in completed if t.exit_reason == "SL"), None)
    assert sl_trade is not None, f"No SL trade found: {completed}"
    assert sl_trade.entry_price == 100.0
    assert sl_trade.exit_price == 98.0
    assert sl_trade.exit_reason == "SL"


# ---------------------------------------------------------------------------
# Test 3: TIME exit fires after max_holding_hours (bar-count, not date math)
# ---------------------------------------------------------------------------

def test_time_exit_after_max_holding_bars():
    from tradingagents.backtesting.types import OrderIntent
    bars = [
        Bar("2024-01-01", 100, 100, 100, 100),
        Bar("2024-01-02", 100, 100, 100, 100),   # entry at open 100, bars_held=1
        Bar("2024-01-03", 100, 100, 100, 100),   # bars_held=2 -> TIME (48h/1d = 2 bars)
        Bar("2024-01-04", 100, 100, 100, 100),
    ]
    provider = FakeBarProvider({"AAPL": bars})

    class TimeModel:
        def build_order(self, decision, spec, bar, equity):
            if decision.rating == PortfolioRating.BUY:
                return OrderIntent(side="BUY", volume=10, entry_price=bar.close,
                                   stop_loss=None, take_profit=None, max_holding_hours=48)
            return None

    class OnceController:
        def __init__(self):
            self._seen = set()
        def decide(self, symbol, date):
            if date in self._seen:
                return PortfolioDecision(rating=PortfolioRating.HOLD, executive_summary="",
                                         investment_thesis="")
            self._seen.add(date)
            return PortfolioDecision(rating=PortfolioRating.BUY, executive_summary="",
                                     investment_thesis="")

    config = BacktestConfig(ticker="AAPL", start_date="2024-01-01", end_date="2024-01-04",
                            cadence_bars=1, initial_capital=10_000.0, timeframe="1d")
    engine = BacktestEngine(config=config, spec=EQ, provider=provider,
                            controller=OnceController(), position_model=TimeModel())
    result = engine.run()
    assert result.trades[0].exit_reason == "TIME"
    assert result.trades[0].exit_date == "2024-01-03"
