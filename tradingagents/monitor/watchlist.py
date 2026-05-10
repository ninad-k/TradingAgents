"""
Watchlist configuration for continuous monitoring.

Defines which symbols to monitor, at what interval, and with which analysts.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

from tradingagents.monitor.symbols import detect_symbol_mode, get_symbol_display_name, is_tradingview_symbol


@dataclass
class WatchlistEntry:
    """Configuration for a single monitored symbol."""
    symbol: str
    display_name: str
    mode: str              # "forex", "commodity", "stock"
    interval_hours: int    # How often to run analysis
    analysts: List[str]    # Which analysts to enable
    use_tradingview: bool  # Whether to use TradingView as data source
    enabled: bool = True
    last_analysis: Optional[datetime] = None
    last_decision: Optional[str] = None
    last_signal: Optional[str] = None  # BUY / HOLD / SELL


# Default forex/commodity analyst set (no fundamentals — not applicable)
FOREX_ANALYSTS = ["market"]  # Technical analysis only for forex
# News can also be included but fundamentals/social not applicable to fx pairs
FOREX_ANALYSTS_WITH_NEWS = ["market", "news"]

# Default stock analyst set
STOCK_ANALYSTS = ["market", "social", "news", "fundamentals"]


def _make_entry(symbol: str, interval_hours: int = 4, include_news: bool = False) -> WatchlistEntry:
    """Create a WatchlistEntry for a given symbol with sensible defaults."""
    mode = detect_symbol_mode(symbol)
    use_tv = is_tradingview_symbol(symbol)

    if mode in ("forex", "commodity"):
        analysts = FOREX_ANALYSTS_WITH_NEWS if include_news else FOREX_ANALYSTS
    else:
        analysts = STOCK_ANALYSTS

    return WatchlistEntry(
        symbol=symbol.upper(),
        display_name=get_symbol_display_name(symbol),
        mode=mode,
        interval_hours=interval_hours,
        analysts=analysts,
        use_tradingview=use_tv,
    )


class Watchlist:
    """Manages the list of monitored symbols."""

    def __init__(self):
        """Initialize with default watchlist."""
        self._entries: Dict[str, WatchlistEntry] = {}
        self._load_defaults()

    def _load_defaults(self):
        """Load the default watchlist (XAUUSD + major forex pairs)."""
        defaults = [
            # Gold — start here per user request
            ("XAUUSD", 4, True),   # Every 4 hours, include news
            # Major forex pairs
            ("EURUSD", 4, False),
            ("GBPUSD", 4, False),
            ("USDJPY", 4, False),
            ("USDCHF", 4, False),
            ("AUDUSD", 4, False),
        ]
        for symbol, hours, news in defaults:
            entry = _make_entry(symbol, hours, news)
            self._entries[symbol] = entry

    def add(self, symbol: str, interval_hours: int = 4, include_news: bool = False) -> WatchlistEntry:
        """Add a symbol to the watchlist."""
        entry = _make_entry(symbol, interval_hours, include_news)
        self._entries[symbol.upper()] = entry
        return entry

    def remove(self, symbol: str) -> bool:
        """Remove a symbol from the watchlist."""
        sym = symbol.upper()
        if sym in self._entries:
            del self._entries[sym]
            return True
        return False

    def get(self, symbol: str) -> Optional[WatchlistEntry]:
        """Get a watchlist entry by symbol."""
        return self._entries.get(symbol.upper())

    def all(self) -> List[WatchlistEntry]:
        """Get all watchlist entries."""
        return list(self._entries.values())

    def enabled(self) -> List[WatchlistEntry]:
        """Get enabled entries."""
        return [e for e in self._entries.values() if e.enabled]

    def due_for_analysis(self) -> List[WatchlistEntry]:
        """Return entries that haven't been analyzed recently enough."""
        from datetime import timezone
        now = datetime.now()
        due = []
        for entry in self.enabled():
            if entry.last_analysis is None:
                due.append(entry)
            else:
                elapsed = now - entry.last_analysis
                if elapsed.total_seconds() >= entry.interval_hours * 3600:
                    due.append(entry)
        return due

    def update_result(self, symbol: str, decision: str, signal: str):
        """Update the last analysis result for a symbol."""
        entry = self.get(symbol)
        if entry:
            entry.last_analysis = datetime.now()
            entry.last_decision = decision
            entry.last_signal = signal

    def to_dict_list(self) -> List[Dict]:
        """Serialize watchlist to list of dicts (for API)."""
        return [
            {
                "symbol": e.symbol,
                "display_name": e.display_name,
                "mode": e.mode,
                "interval_hours": e.interval_hours,
                "analysts": e.analysts,
                "use_tradingview": e.use_tradingview,
                "enabled": e.enabled,
                "last_analysis": e.last_analysis.isoformat() if e.last_analysis else None,
                "last_decision": e.last_decision,
                "last_signal": e.last_signal,
            }
            for e in self._entries.values()
        ]


# Global singleton watchlist instance
watchlist = Watchlist()
