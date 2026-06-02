from typing import Annotated

# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .tradingview import get_tradingview_data, get_tradingview_indicators
from .mt5_market_data import get_mt5_market_data

# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    }
}

VENDOR_LIST = [
    "tradingview",
    "mt5",
    "yfinance",
    "alpha_vantage",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis — priority: tradingview → mt5 → yfinance → alpha_vantage
    "get_stock_data": {
        "tradingview": get_tradingview_data,
        "mt5": get_mt5_market_data,
        "yfinance": get_YFin_data_online,
        "alpha_vantage": get_alpha_vantage_stock,
    },
    # technical_indicators — MT5 doesn't expose indicators directly, so the
    # chain skips it for this method and falls straight from TV to yfinance.
    "get_indicators": {
        "tradingview": get_tradingview_indicators,
        "yfinance": get_stock_stats_indicators_window,
        "alpha_vantage": get_alpha_vantage_indicator,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
}

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

_FAILURE_RESPONSE_MARKERS = (
    "no tradingview data",
    "error fetching",
    "no mt5 data",
    "no data found",
    "not found",
    "symbol may not exist",
    "terminal not connected",
    # Library-missing sentinels (e.g. tradingview-datafeed not pip-installed).
    "not installed",
    "tradingview datafeed",
    "metatrader5 library not installed",
    "import error",
)


def _looks_like_failure(result) -> bool:
    """Some vendors swallow exceptions and return an error *string* instead of
    raising. Detect those so the fallback chain can advance to the next vendor.
    """
    if result is None:
        return True
    if not isinstance(result, str):
        return False
    head = result.strip().lower()[:240]
    return any(marker in head for marker in _FAILURE_RESPONSE_MARKERS)


def route_to_vendor(method: str, *args, **kwargs):
    """Route a tool call through the configured vendor chain.

    Behavior: read the configured comma-separated vendor list (e.g.
    ``"tradingview,mt5,yfinance"``) for this method's category, append any
    remaining registered vendors as automatic fallback, and try each in order.
    Advance to the next vendor when the current one (a) raises, or (b) returns
    a string that looks like a "no data / error" sentinel — historically some
    vendors swallow exceptions and the fallback never fired.
    """
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',') if v.strip()]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = list(primary_vendors)
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    last_failure_text = None
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            result = impl_func(*args, **kwargs)
        except AlphaVantageRateLimitError:
            last_failure_text = f"{vendor}: rate-limited"
            continue
        except Exception as e:  # noqa: BLE001 — yes, we deliberately catch all
            last_failure_text = f"{vendor}: {e}"
            continue

        if _looks_like_failure(result):
            # Keep the sentinel text in case nobody else succeeds — useful for
            # surfacing the root cause back to the analyst LLM.
            last_failure_text = f"{vendor}: {str(result)[:200]}"
            continue

        return result

    return (
        f"No vendor returned data for '{method}'. "
        f"Last failure: {last_failure_text or 'unknown'}"
    )