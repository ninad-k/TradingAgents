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
