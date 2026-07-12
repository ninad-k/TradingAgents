"""Transaction-cost model: trade_cost, apply_slippage, and net-vs-gross PnL."""
from __future__ import annotations

from tradingagents.backtesting.portfolio import Portfolio
from tradingagents.backtesting.types import (
    InstrumentKind,
    InstrumentSpec,
    apply_slippage,
    trade_cost,
)

# Zero-cost vs costed specs for the same instrument.
EQ_FREE = InstrumentSpec("AAPL", InstrumentKind.EQUITY, 0.01, 0.0, 1, 1e9, 1, 0.0)
EQ_COST = InstrumentSpec("AAPL", InstrumentKind.EQUITY, 0.01, 0.0, 1, 1e9, 1, 0.0,
                         commission_rate=0.001, min_commission=1.0, slippage_points=2.0)
FX_FREE = InstrumentSpec("XAUUSD", InstrumentKind.FOREX, 0.01, 1.0, 0.01, 100, 0.01, 30.0)
FX_COST = InstrumentSpec("XAUUSD", InstrumentKind.FOREX, 0.01, 1.0, 0.01, 100, 0.01, 30.0,
                         commission_per_lot=3.5, slippage_points=5.0)


def test_zero_cost_spec_is_free():
    assert trade_cost(EQ_FREE, price=100.0, volume=10) == 0.0
    assert trade_cost(FX_FREE, price=2000.0, volume=1.0) == 0.0
    assert apply_slippage(EQ_FREE, "BUY", 100.0) == 100.0
    assert apply_slippage(FX_FREE, "SELL", 2000.0) == 2000.0


def test_equity_commission_rate_and_floor():
    # 0.1% of 100*100 = 10.0 (well above the 1.0 floor).
    assert trade_cost(EQ_COST, price=100.0, volume=100) == 10.0
    # Tiny notional (0.1% of 1 = 0.001) gets floored to min_commission.
    assert trade_cost(EQ_COST, price=1.0, volume=1) == 1.0


def test_forex_commission_per_lot():
    assert trade_cost(FX_COST, price=2000.0, volume=2.0) == 7.0  # 3.5 * 2 lots


def test_slippage_is_adverse_by_market_action():
    # point=0.01, slippage_points=2 -> 0.02 adverse move.
    assert apply_slippage(EQ_COST, "BUY", 100.0) == 100.02
    assert apply_slippage(EQ_COST, "SELL", 100.0) == 99.98


def test_round_trip_net_below_gross_by_exact_cost():
    # A flat round-trip (entry==exit price) should lose exactly the commission.
    pf = Portfolio(initial_capital=100_000.0, spec=EQ_COST)
    pf.open(side="BUY", date="2024-01-01", price=100.0, volume=100)
    trade = pf.close(date="2024-01-02", price=100.0, reason="TP")
    assert trade.gross_pnl == 0.0
    assert trade.entry_cost == 10.0          # 0.1% of 100*100
    assert trade.cost == 20.0                # entry + exit
    assert trade.pnl == -20.0                # net = gross - cost
    assert trade.pnl == trade.gross_pnl - trade.cost
    # Equity reflects the net loss.
    assert pf.equity(100.0) == 100_000.0 - 20.0


def test_zero_cost_round_trip_matches_legacy():
    pf = Portfolio(initial_capital=100_000.0, spec=EQ_FREE)
    pf.open(side="BUY", date="2024-01-01", price=100.0, volume=10)
    trade = pf.close(date="2024-01-02", price=110.0, reason="TP")
    assert trade.cost == 0.0
    assert trade.pnl == trade.gross_pnl == 100.0   # (110-100)*10, no friction
