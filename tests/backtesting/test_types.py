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


def test_forex_pnl_short():
    spec = InstrumentSpec(symbol="XAUUSD", kind=InstrumentKind.FOREX,
                          point=0.01, pip_value_per_lot=1.0,
                          min_volume=0.01, max_volume=100, volume_step=0.01,
                          spread_points=30.0)
    # short: price drops 1.00 -> +100 points * 1.0 * 1 lot = +100.0
    assert position_pnl(spec, "SELL", entry_price=2001.0, exit_price=2000.0, volume=1.0) == 100.0
