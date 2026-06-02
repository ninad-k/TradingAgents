"""
TradingView data provider using tvdatafeed.

Fetches OHLCV data directly from TradingView for forex pairs, commodities,
and other instruments not well-supported by yfinance.

Install: pip install tradingview-datafeed
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional
import pandas as pd

logger = logging.getLogger(__name__)

# TradingView exchange mapping for known forex/commodity symbols
TV_EXCHANGE_MAP = {
    # Precious metals (commodities)
    "XAUUSD": "OANDA",   # Gold vs USD
    "XAGUSD": "OANDA",   # Silver vs USD
    "XPTUSD": "OANDA",   # Platinum vs USD
    "XPDUSD": "OANDA",   # Palladium vs USD

    # Major forex pairs
    "EURUSD": "OANDA",
    "GBPUSD": "OANDA",
    "USDJPY": "OANDA",
    "USDCHF": "OANDA",
    "USDCAD": "OANDA",
    "AUDUSD": "OANDA",
    "NZDUSD": "OANDA",

    # Minor forex pairs
    "EURGBP": "OANDA",
    "EURJPY": "OANDA",
    "GBPJPY": "OANDA",
    "AUDJPY": "OANDA",
    "CADJPY": "OANDA",
    "NZDJPY": "OANDA",
    "EURCHF": "OANDA",
    "GBPCHF": "OANDA",
    "EURAUD": "OANDA",
    "GBPAUD": "OANDA",
    "EURCAD": "OANDA",
    "GBPCAD": "OANDA",

    # Exotic forex pairs
    "USDZAR": "OANDA",
    "USDMXN": "OANDA",
    "USDSEK": "OANDA",
    "USDNOK": "OANDA",
    "USDDKK": "OANDA",
    "USDSGD": "OANDA",
    "USDHKD": "OANDA",
}


def _get_tv_client():
    """Get TradingView data feed client."""
    try:
        from tvDatafeed import TvDatafeed
        return TvDatafeed()
    except ImportError:
        raise ImportError(
            "TradingView datafeed is not installed. Run: pip install tradingview-datafeed"
        )


def _get_tv_interval(days_range: int):
    """Select appropriate TradingView interval based on date range requested."""
    try:
        from tvDatafeed import Interval
        if days_range <= 5:
            return Interval.in_15_minute, 5 * 24 * 4   # 15-min bars
        elif days_range <= 30:
            return Interval.in_1_hour, days_range * 24  # 1h bars
        elif days_range <= 90:
            return Interval.in_4_hour, days_range * 6   # 4h bars
        else:
            return Interval.in_daily, days_range + 30   # Daily bars
    except ImportError:
        raise ImportError("TradingView datafeed is not installed. Run: pip install tradingview-datafeed")


def _resolve_exchange(symbol: str) -> str:
    """Resolve TradingView exchange for a given symbol."""
    sym = symbol.upper().strip()
    return TV_EXCHANGE_MAP.get(sym, "OANDA")  # Default to OANDA for unknown pairs


def get_tradingview_data(
    symbol: Annotated[str, "Symbol to fetch (e.g. XAUUSD, EURUSD)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Fetch OHLCV data from TradingView for forex pairs and commodities.
    Returns CSV-formatted string matching the interface expected by the analysis pipeline.
    """
    try:
        tv = _get_tv_client()

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        days_range = (end - start).days

        interval, n_bars = _get_tv_interval(days_range)
        exchange = _resolve_exchange(symbol)

        logger.info(f"Fetching TradingView data: {symbol} from {exchange}, {n_bars} bars")

        data = tv.get_hist(
            symbol=symbol.upper(),
            exchange=exchange,
            interval=interval,
            n_bars=n_bars,
            fut_contract=None,
        )

        if data is None or data.empty:
            return f"No TradingView data found for {symbol} on {exchange}. Ensure the symbol is correct."

        # Filter to requested date range
        data.index = pd.to_datetime(data.index)
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)

        data = data[(data.index >= start) & (data.index <= end + timedelta(days=1))]

        # Rename to match yfinance convention
        data = data.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })

        # Round to 5 decimal places (forex pip precision)
        for col in ["Open", "High", "Low", "Close"]:
            if col in data.columns:
                data[col] = data[col].round(5)

        csv_string = data.to_csv()
        header = f"# TradingView data for {symbol.upper()} from {start_date} to {end_date}\n"
        header += f"# Exchange: {exchange} | Records: {len(data)}\n"
        header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except ImportError as e:
        return str(e)
    except Exception as e:
        logger.error(f"TradingView data fetch error for {symbol}: {e}")
        return f"Error fetching TradingView data for {symbol}: {e}"


def get_tradingview_indicators(
    symbol: Annotated[str, "Symbol (e.g. XAUUSD, EURUSD)"],
    indicator: Annotated[str, "Comma-separated indicator names"],
    curr_date: Annotated[str, "Current trading date YYYY-mm-dd"],
    look_back_days: Annotated[int, "Days to look back"] = 60,
) -> str:
    """
    Compute technical indicators on TradingView OHLCV data.
    Uses the same stockstats-based implementation as yfinance indicators.
    """
    try:
        from tradingagents.dataflows.stockstats_utils import StockstatsUtils

        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=look_back_days + 60)  # extra buffer

        start_date = start_dt.strftime("%Y-%m-%d")
        end_date = end_dt.strftime("%Y-%m-%d")

        tv = _get_tv_client()
        interval, n_bars = _get_tv_interval(look_back_days + 60)
        exchange = _resolve_exchange(symbol)

        data = tv.get_hist(
            symbol=symbol.upper(),
            exchange=exchange,
            interval=interval,
            n_bars=n_bars,
        )

        if data is None or data.empty:
            return f"No TradingView data to compute indicators for {symbol}."

        data.index = pd.to_datetime(data.index)
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)

        # Rename to what stockstats expects
        data = data.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })

        # Filter to date range
        data = data[data.index <= end_dt + timedelta(days=1)]

        # Compute each indicator
        indicators = [ind.strip() for ind in indicator.split(",")]
        results = []

        for ind in indicators:
            try:
                result = StockstatsUtils.get_stat(
                    data.copy(), ind, curr_date, look_back_days
                )
                results.append(f"## {ind} for {symbol}:\n{result}")
            except Exception as e:
                results.append(f"## {ind} for {symbol}: Error — {e}")

        return "\n\n".join(results)

    except ImportError as e:
        return str(e)
    except Exception as e:
        logger.error(f"TradingView indicator error for {symbol}/{indicator}: {e}")
        return f"Error computing indicators for {symbol}: {e}"
