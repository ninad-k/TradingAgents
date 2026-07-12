"""
Minimal close-price lookup for outcome evaluation.

Returns a single close price for ``(symbol, timestamp)``. Forex/commodity
symbols go through TradingView (tvdatafeed); equity tickers go through
yfinance. Failures return ``None`` rather than raising — the outcome
evaluator records the error and moves on.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from tradingagents.monitor.symbols import is_tradingview_symbol

logger = logging.getLogger(__name__)


def get_close_at(symbol: str, ts: datetime) -> Optional[float]:
    """Return the close price at-or-just-before ``ts``, or None on failure.

    Primary sources: TvDatafeed (forex/commodity/crypto) or yfinance (equities).
    If both fail, falls back to the MT5 broker's live bid price so that
    "evaluate now" can compute unrealized PnL even when data feeds are unavailable.
    """
    sym = symbol.upper().strip()
    price = None
    try:
        if is_tradingview_symbol(sym):
            price = _tv_close_at(sym, ts)
        else:
            price = _yf_close_at(sym, ts)
    except Exception as e:
        logger.warning("Price lookup failed for %s @ %s: %s", sym, ts, e)

    if price is not None:
        return price

    # Fallback: ask the MT5 broker for the current live bid price.
    # This is good enough for "unrealized PnL if closed now" calculations.
    return _broker_price_fallback(sym)


def _broker_price_fallback(symbol: str) -> Optional[float]:
    """Return the broker's current bid price for ``symbol``, or None."""
    try:
        from tradingagents.brokers.mt5_connector import get_shared_mt5_connector
        connector = get_shared_mt5_connector()
        info = connector.get_symbol_info(symbol)
        if info and info.bid:
            logger.debug("Price fallback via broker for %s: %.5f", symbol, info.bid)
            return float(info.bid)
    except Exception as e:
        logger.debug("Broker price fallback failed for %s: %s", symbol, e)
    return None


def _tv_close_at(symbol: str, ts: datetime) -> Optional[float]:
    from tvDatafeed import TvDatafeed, Interval

    from tradingagents.dataflows.tradingview import TV_EXCHANGE_MAP

    tv = TvDatafeed()
    exchange = TV_EXCHANGE_MAP.get(symbol, "OANDA")
    # 1h bars across a 14-day window are enough to bracket a 24h horizon
    # with margin for weekends/holidays.
    df = tv.get_hist(
        symbol=symbol,
        exchange=exchange,
        interval=Interval.in_1_hour,
        n_bars=24 * 14,
    )
    if df is None or df.empty:
        return None
    return _last_close_at_or_before(df, ts, close_col="close")


def _yf_close_at(symbol: str, ts: datetime) -> Optional[float]:
    import yfinance as yf

    start = (ts - timedelta(days=10)).strftime("%Y-%m-%d")
    end = (ts + timedelta(days=2)).strftime("%Y-%m-%d")
    df = yf.Ticker(symbol).history(start=start, end=end, interval="1h")
    if df is None or df.empty:
        df = yf.Ticker(symbol).history(start=start, end=end)
    if df is None or df.empty:
        return None
    return _last_close_at_or_before(df, ts, close_col="Close")


def _last_close_at_or_before(df, ts: datetime, close_col: str) -> Optional[float]:
    import pandas as pd

    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df = df.copy()
    df.index = idx
    mask = df.index <= ts
    if not mask.any():
        # All bars are after ts — fall back to the earliest available.
        row = df.iloc[0]
    else:
        row = df.loc[mask].iloc[-1]
    val = row.get(close_col)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
