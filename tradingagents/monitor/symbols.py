"""
Symbol classification: detect forex, commodity, and stock instruments.
Used to configure the correct data vendor and analysis mode.
"""

from typing import Literal

SymbolMode = Literal["forex", "commodity", "stock"]

# Known forex pairs (6-char, no exchange suffix)
FOREX_PAIRS = {
    # Majors
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    # Minors
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "NZDJPY",
    "EURCHF", "GBPCHF", "EURAUD", "GBPAUD", "EURCAD", "GBPCAD",
    "AUDCAD", "AUDCHF", "AUDNZD", "NZDCAD", "NZDCHF",
    # Exotics
    "USDZAR", "USDMXN", "USDSEK", "USDNOK", "USDDKK",
    "USDSGD", "USDHKD", "USDTRY", "USDPLN", "USDHUF",
    "EURNOK", "EURSEK", "EURPLN", "EURHUF",
}

# Precious metals and spot commodities (quoted vs USD on OANDA/TradingView)
COMMODITY_PAIRS = {
    "XAUUSD",  # Gold
    "XAGUSD",  # Silver
    "XPTUSD",  # Platinum
    "XPDUSD",  # Palladium
    "XBRUSD",  # Brent crude (some brokers)
    "XTIUSD",  # WTI crude (some brokers)
}

# All TradingView-native symbols (forex + commodities)
TRADINGVIEW_SYMBOLS = FOREX_PAIRS | COMMODITY_PAIRS


def detect_symbol_mode(symbol: str) -> SymbolMode:
    """Detect whether a symbol is forex, commodity, or a regular stock."""
    sym = symbol.upper().strip()

    if sym in COMMODITY_PAIRS:
        return "commodity"
    if sym in FOREX_PAIRS:
        return "forex"

    # Heuristic: 6-char all-alpha symbol that looks like a pair
    if len(sym) == 6 and sym.isalpha():
        # Could be an unlisted forex pair
        return "forex"

    return "stock"


def is_tradingview_symbol(symbol: str) -> bool:
    """Return True if this symbol should use TradingView as the data source."""
    return detect_symbol_mode(symbol) in ("forex", "commodity")


def get_symbol_display_name(symbol: str) -> str:
    """Get a human-readable name for a symbol."""
    names = {
        "XAUUSD": "Gold / USD",
        "XAGUSD": "Silver / USD",
        "XPTUSD": "Platinum / USD",
        "EURUSD": "EUR / USD",
        "GBPUSD": "GBP / USD",
        "USDJPY": "USD / JPY",
        "USDCHF": "USD / CHF",
        "USDCAD": "USD / CAD",
        "AUDUSD": "AUD / USD",
        "NZDUSD": "NZD / USD",
        "EURGBP": "EUR / GBP",
        "EURJPY": "EUR / JPY",
        "GBPJPY": "GBP / JPY",
    }
    return names.get(symbol.upper(), symbol.upper())
