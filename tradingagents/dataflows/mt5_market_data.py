"""
MT5 market data vendor.

Fetches OHLCV bars directly from the attached MetaTrader 5 terminal so the
Market Analyst can use broker-native data for any symbol the broker exposes
(2500+ instruments on a typical ICMarkets-style demo). Sits in the vendor
chain between TradingView (when available) and yfinance (last-resort
fallback).

Output mirrors the TradingView/yfinance shape: a CSV string with `Open,
High, Low, Close, Volume` columns and a small header for provenance, so
downstream code (technical indicators, the analyst LLM prompt) doesn't care
which vendor produced it.
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Annotated, Optional

import logging
logger = logging.getLogger(__name__)


def _pick_timeframe(days_range: int):
    """Map a date-range span to an MT5 timeframe enum + bar count.

    Same philosophy as TradingView's picker: short windows use fine-grained
    bars, long windows roll up to daily so we don't drown the analyst.
    """
    import MetaTrader5 as mt5
    if days_range <= 5:
        return mt5.TIMEFRAME_M15, days_range * 96  # 96 = 24h * 4 bars/h
    if days_range <= 30:
        return mt5.TIMEFRAME_H1, days_range * 24
    if days_range <= 180:
        return mt5.TIMEFRAME_H4, days_range * 6
    return mt5.TIMEFRAME_D1, days_range


# How many recent bars to pull when an explicit intraday timeframe is forced.
# Intraday windows are anchored to "now" (copy_rates_from_pos) rather than the
# analyst's multi-day date range, which for M1 would be tens of thousands of bars.
_EXPLICIT_TF_BARS = {
    "M1": 500, "M5": 500, "M15": 400, "M30": 400,
    "H1": 300, "H4": 200, "D1": 250,
}


def _explicit_timeframe():
    """Resolve a forced ``market_timeframe`` from config, if any.

    Returns ``(tf_enum, tf_label, bar_count)`` when an explicit MT5 timeframe is
    configured (e.g. "M1"), else ``None`` so the caller uses the date-range
    picker. "auto"/empty means no override.
    """
    try:
        from tradingagents.dataflows.config import get_config
        tf_label = str((get_config() or {}).get("market_timeframe", "auto") or "auto").upper()
    except Exception:
        tf_label = "AUTO"
    if tf_label in ("", "AUTO"):
        return None
    import MetaTrader5 as mt5
    tf_enum = getattr(mt5, f"TIMEFRAME_{tf_label}", None)
    if tf_enum is None:
        logger.warning("Unknown market_timeframe %r; falling back to auto picker", tf_label)
        return None
    return tf_enum, tf_label, _EXPLICIT_TF_BARS.get(tf_label, 400)


def get_mt5_market_data(
    symbol: Annotated[str, "Symbol to fetch (e.g. XAUUSD, EURUSD)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd"],
    end_date: Annotated[str, "End date in yyyy-mm-dd"],
) -> str:
    """Fetch OHLCV from the connected MT5 terminal.

    Raises on hard failure so ``route_to_vendor`` can fall through to the
    next vendor. Returns a CSV string with header on success.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError as e:
        raise RuntimeError(f"MetaTrader5 library not installed: {e}")

    from tradingagents.brokers.mt5_connector import get_shared_mt5_connector
    connector = get_shared_mt5_connector()
    if not connector.is_connected() and not connector.connect():
        raise RuntimeError("MT5 terminal not connected; cannot fetch bars")

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    except ValueError as e:
        raise ValueError(f"Bad date in MT5 fetch: {e}")

    days_range = max(1, (end - start).days)

    # Make sure the symbol is visible in Market Watch — MT5 won't return rates
    # for hidden symbols. Selecting is idempotent.
    sym_upper = symbol.upper()
    try:
        if not mt5.symbol_select(sym_upper, True):
            raise RuntimeError(
                f"MT5 symbol_select({sym_upper}) failed; symbol may not exist on broker"
            )
    except Exception as e:
        raise RuntimeError(f"MT5 symbol_select error for {sym_upper}: {e}")

    forced = _explicit_timeframe()
    if forced is not None:
        # Explicit intraday timeframe (e.g. M1): pull the most recent N bars
        # ending at "now" rather than the analyst's multi-day date range.
        timeframe, _forced_label, count = forced
        rates = mt5.copy_rates_from_pos(sym_upper, timeframe, 0, count)
    else:
        timeframe, _ = _pick_timeframe(days_range)
        rates = mt5.copy_rates_range(sym_upper, timeframe, start, end)
    if rates is None or len(rates) == 0:
        err = mt5.last_error() if hasattr(mt5, "last_error") else None
        raise RuntimeError(
            f"MT5 returned no bars for {sym_upper} {start_date}..{end_date} "
            f"(timeframe={timeframe}); last_error={err}"
        )

    # Build CSV in the same shape as TradingView / yfinance output.
    try:
        import pandas as pd
    except ImportError as e:
        raise RuntimeError(f"pandas required for MT5 vendor: {e}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")
    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "tick_volume": "Volume",
    })
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col].round(5)

    tf_label = {
        getattr(mt5, "TIMEFRAME_M1"):  "M1",
        getattr(mt5, "TIMEFRAME_M5"):  "M5",
        getattr(mt5, "TIMEFRAME_M15"): "M15",
        getattr(mt5, "TIMEFRAME_M30"): "M30",
        getattr(mt5, "TIMEFRAME_H1"):  "H1",
        getattr(mt5, "TIMEFRAME_H4"):  "H4",
        getattr(mt5, "TIMEFRAME_D1"):  "D1",
    }.get(timeframe, str(timeframe))

    header = (
        f"# MT5 data for {sym_upper} from {start_date} to {end_date}\n"
        f"# Source: attached terminal | Timeframe: {tf_label} | Records: {len(df)}\n"
        f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + df.to_csv()
