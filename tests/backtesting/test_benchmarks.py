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
