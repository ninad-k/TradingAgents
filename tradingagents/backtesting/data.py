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

INSTRUMENT_SPECS = dict(_FOREX_SPECS)


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
        from datetime import datetime, timedelta
        import yfinance as yf
        # yfinance treats `end` as exclusive; advance one day so the requested
        # end date is included, matching the other providers' inclusive range.
        end_excl = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        hist = yf.Ticker(symbol).history(start=start, end=end_excl, interval=timeframe)
        out = []
        for ts, row in hist.iterrows():
            date = ts.strftime("%Y-%m-%d")
            if start <= date <= end:
                out.append(Bar(date=date, open=float(row["Open"]),
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
        if timeframe not in self._INTERVALS:
            raise ValueError(f"Unsupported timeframe {timeframe!r}; expected one of {sorted(self._INTERVALS)}")
        interval = getattr(Interval, self._INTERVALS[timeframe])
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
