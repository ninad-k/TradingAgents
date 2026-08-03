"""Agent tool exposing the deterministic liquidity scanner."""

from typing import Annotated

from langchain_core.tools import tool


@tool
def get_liquidity_map(
    symbol: Annotated[str, "Ticker/symbol to scan, e.g. BTCUSD, XAUUSD, EURUSD"],
) -> str:
    """Scan all timeframes (M1, M5, M15, H1, H4, D1) for liquidity structure:
    equal highs/lows (liquidity pools), recent liquidity sweeps (stop hunts),
    market structure (bullish/bearish/range), and premium/discount zones.
    The result is COMPUTED from live broker OHLC data — cite its levels and
    sweeps verbatim; do not invent levels that are not in this table."""
    from tradingagents.analytics.liquidity import build_liquidity_map

    try:
        return build_liquidity_map(symbol).to_markdown()
    except Exception as exc:
        return f"Liquidity map unavailable for {symbol}: {exc}"
