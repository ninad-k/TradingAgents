"""
Watchlist configuration for continuous monitoring.

Defines which symbols to monitor, at what interval, and with which analysts.

Backed by `tradingagents.monitor.store` (SQLite) so the FastAPI dashboard
process and the standalone scheduler worker see the same watchlist.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from tradingagents.monitor.symbols import (
    detect_symbol_mode,
    get_symbol_display_name,
    is_tradingview_symbol,
)
from tradingagents.monitor import store


@dataclass
class WatchlistEntry:
    """Configuration for a single monitored symbol."""
    symbol: str
    display_name: str
    mode: str              # "forex", "commodity", "stock"
    interval_hours: int
    analysts: List[str]
    use_tradingview: bool
    enabled: bool = True
    last_analysis: Optional[datetime] = None
    last_decision: Optional[str] = None
    last_signal: Optional[str] = None


# Default forex/commodity analyst set (no fundamentals — not applicable)
FOREX_ANALYSTS = ["market"]
FOREX_ANALYSTS_WITH_NEWS = ["market", "news"]
STOCK_ANALYSTS = ["market", "social", "news", "fundamentals"]


def _make_entry(symbol: str, interval_hours: int = 4, include_news: bool = False) -> WatchlistEntry:
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


def _entry_from_row(row: Dict) -> WatchlistEntry:
    return WatchlistEntry(
        symbol=row["symbol"],
        display_name=row["display_name"],
        mode=row["mode"],
        interval_hours=row["interval_hours"],
        analysts=row["analysts"],
        use_tradingview=row["use_tradingview"],
        enabled=row["enabled"],
        last_analysis=row["last_analysis"],
        last_decision=row["last_decision"],
        last_signal=row["last_signal"],
    )


_DEFAULT_SEED = [
    # Gold — start here per user request
    ("XAUUSD", 4, True),
    # Major forex pairs
    ("EURUSD", 4, False),
    ("GBPUSD", 4, False),
    ("USDJPY", 4, False),
    ("USDCHF", 4, False),
    ("AUDUSD", 4, False),
]


class Watchlist:
    """Read-through wrapper around the SQLite watchlist store."""

    def __init__(self):
        self._seed_if_empty()

    def _seed_if_empty(self) -> None:
        if store.watchlist_count() > 0:
            return
        for symbol, hours, news in _DEFAULT_SEED:
            store.save_watchlist_entry(_make_entry(symbol, hours, news))

    def add(self, symbol: str, interval_hours: int = 4, include_news: bool = False) -> WatchlistEntry:
        entry = _make_entry(symbol, interval_hours, include_news)
        store.save_watchlist_entry(entry)
        return entry

    def remove(self, symbol: str) -> bool:
        return store.delete_watchlist_entry(symbol)

    def get(self, symbol: str) -> Optional[WatchlistEntry]:
        row = store.get_watchlist_row(symbol)
        return _entry_from_row(row) if row else None

    def all(self) -> List[WatchlistEntry]:
        return [_entry_from_row(row) for row in store.load_watchlist_rows()]

    def enabled(self) -> List[WatchlistEntry]:
        return [e for e in self.all() if e.enabled]

    def due_for_analysis(self) -> List[WatchlistEntry]:
        now = datetime.now()
        due = []
        for entry in self.enabled():
            if entry.last_analysis is None:
                due.append(entry)
                continue
            elapsed = now - entry.last_analysis
            if elapsed.total_seconds() >= entry.interval_hours * 3600:
                due.append(entry)
        return due

    def update_result(self, symbol: str, decision: str, signal: str) -> None:
        entry = self.get(symbol)
        if not entry:
            return
        entry.last_analysis = datetime.now()
        entry.last_decision = decision
        entry.last_signal = signal
        store.save_watchlist_entry(entry)

    def to_dict_list(self) -> List[Dict]:
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
            for e in self.all()
        ]


# Global singleton — both processes import this, both hit the same SQLite file.
watchlist = Watchlist()
