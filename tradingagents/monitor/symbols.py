"""
Symbol classification: detect forex, commodity, crypto, index, or stock.

Used to configure the correct data vendor and analysis mode.

Two-layer strategy:
1. **Broker-first** — when an MT5 terminal is attached, we consult the
   connector's cached symbol catalog (``list_symbols``) and map the broker's
   own category tree onto our ``SymbolMode`` literal. This is the source of
   truth because the broker actually knows where it filed each instrument.
2. **Static fallback** — when no broker is reachable or the symbol isn't in
   the catalog, we fall back to a small lookup of forex/commodity sets plus
   a 6-char-pair heuristic. Same behavior as before this module gained
   broker awareness.
"""

import logging
from typing import Literal, Optional

logger = logging.getLogger(__name__)

SymbolMode = Literal["forex", "commodity", "crypto", "index", "stock"]

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

# Static crypto fallback set — used only when broker catalog is unreachable.
CRYPTO_PAIRS = {
    "BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "BCHUSD",
    "ADAUSD", "SOLUSD", "DOTUSD", "DOGEUSD", "AVAXUSD",
    "MATICUSD", "LINKUSD", "ATOMUSD",
}

# Static index fallback set — common MT5 CFD index tickers.
INDEX_TICKERS = {
    "NAS100", "US500", "US30", "US2000",
    "GER40", "GER30", "DAX40", "UK100", "FRA40", "ESP35", "EU50",
    "JPN225", "HK50", "AUS200", "CHINA50",
    "VIX",
}

# All symbols served by TradingView (forex + commodities + crypto + indices).
TRADINGVIEW_SYMBOLS = FOREX_PAIRS | COMMODITY_PAIRS | CRYPTO_PAIRS | INDEX_TICKERS

# ── Broker category → SymbolMode map ────────────────────────────────────────
# Keys are the top-level folder strings MT5 brokers commonly use. Comparison
# is case-insensitive and ignores stray characters so "Stock CFD's", "STOCKS",
# "stockCFDs" all collapse to the same bucket.
_CATEGORY_TO_MODE: dict[str, SymbolMode] = {
    "forex":       "forex",
    "fx":          "forex",
    "currencies":  "forex",
    "currency":    "forex",
    "metals":      "commodity",
    "metal":       "commodity",
    "commodities": "commodity",
    "commodity":   "commodity",
    "energies":    "commodity",
    "energy":      "commodity",
    "crypto":      "crypto",
    "cryptos":     "crypto",
    "cryptocurrencies": "crypto",
    "indices":     "index",
    "index":       "index",
    "indexes":     "index",
    "stocks":      "stock",
    "stock":       "stock",
    "stockcfds":   "stock",
    "equities":    "stock",
    "shares":      "stock",
    "bondscfds":   "stock",
    "bonds":       "stock",
}


def _normalize(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalpha())


def _mode_from_broker(symbol: str) -> Optional[SymbolMode]:
    """Look up the broker's category for ``symbol``. Returns None if the
    broker catalog isn't available or doesn't list this symbol."""
    try:
        # Local import: avoid a circular dependency at module-load time and
        # keep this module usable in unit tests with no MT5 installed.
        from tradingagents.brokers.mt5_connector import get_shared_mt5_connector
        connector = get_shared_mt5_connector()
        catalog = connector.list_symbols()  # cached after first call
    except Exception as e:
        logger.debug("Broker catalog unavailable for %s: %s", symbol, e)
        return None
    target = symbol.upper().strip()
    for entry in catalog:
        if entry.get("name", "").upper() == target:
            cat = _normalize(entry.get("category", ""))
            mapped = _CATEGORY_TO_MODE.get(cat)
            if mapped:
                return mapped
            # Unknown category — log so we can extend the map.
            logger.info(
                "Unmapped broker category %r for %s; falling back to static rules",
                entry.get("category"), symbol,
            )
            return None
    return None


def detect_symbol_mode(symbol: str) -> SymbolMode:
    """Detect whether a symbol is forex, commodity, crypto, index, or stock.

    Broker catalog wins when reachable; falls back to static rules otherwise.
    """
    sym = symbol.upper().strip()

    broker_mode = _mode_from_broker(sym)
    if broker_mode is not None:
        return broker_mode

    if sym in COMMODITY_PAIRS:
        return "commodity"
    if sym in FOREX_PAIRS:
        return "forex"
    if sym in CRYPTO_PAIRS:
        return "crypto"
    if sym in INDEX_TICKERS:
        return "index"

    # Heuristic: 6-char all-alpha symbol that looks like a pair
    if len(sym) == 6 and sym.isalpha():
        return "forex"

    return "stock"


def is_tradingview_symbol(symbol: str) -> bool:
    """Return True if this symbol should use TradingView as the data source.

    TradingView covers forex, metals/commodities, crypto, and major indices.
    Stocks (CFDs from the broker tree) still go through yfinance.
    """
    return detect_symbol_mode(symbol) in ("forex", "commodity", "crypto", "index")


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
        "BTCUSD": "Bitcoin / USD",
        "ETHUSD": "Ethereum / USD",
        "NAS100": "Nasdaq 100",
        "US500":  "S&P 500",
        "US30":   "Dow Jones 30",
        "GER40":  "DAX 40",
    }
    return names.get(symbol.upper(), symbol.upper())
