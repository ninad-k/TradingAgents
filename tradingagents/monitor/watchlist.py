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
    mode: str              # "forex", "commodity", "crypto", "index", "stock"
    interval_hours: int
    analysts: List[str]
    use_tradingview: bool
    enabled: bool = True
    last_analysis: Optional[datetime] = None
    last_decision: Optional[str] = None
    last_signal: Optional[str] = None


# Analyst lineups per mode. Names match the graph's internal node keys
# (``social`` is the sentiment analyst node — don't rename to ``sentiment``,
# the graph routing breaks). Macro instruments get the same depth as stocks
# minus a custom fundamentals lens handled by fundamentals_analyst.py.
MACRO_ANALYSTS = ["market", "news", "social", "fundamentals"]
STOCK_ANALYSTS = ["market", "social", "news", "fundamentals"]
# Kept for backward-compatible imports.
MACRO_ANALYSTS_WITH_NEWS = MACRO_ANALYSTS
FAST_ANALYSTS = ["market"]


def _analysts_for_mode(mode: str) -> List[str]:
    """Pick the default analyst lineup based on instrument mode.

    Auto-heals legacy single-analyst rows: any existing row read back from the
    store gets re-classified here, so stored ``analysts=["market"]`` rows from
    the old default automatically gain news + sentiment + fundamentals on next
    load without needing a migration step. Stocks and macro instruments share
    the same node names so the LangGraph wiring is identical.
    """
    if mode == "stock":
        return list(STOCK_ANALYSTS)
    return list(MACRO_ANALYSTS)


def _make_entry(symbol: str, interval_hours: int = 4, include_news: bool = False) -> WatchlistEntry:
    """Build a WatchlistEntry with the right analyst lineup for the symbol."""
    mode = detect_symbol_mode(symbol)
    use_tv = is_tradingview_symbol(symbol)

    return WatchlistEntry(
        symbol=symbol.upper(),
        display_name=get_symbol_display_name(symbol),
        mode=mode,
        interval_hours=interval_hours,
        analysts=_analysts_for_mode(mode),
        use_tradingview=use_tv,
    )


def _entry_from_row(row: Dict) -> WatchlistEntry:
    """Hydrate from the persisted row but always re-derive the analyst lineup.

    The store still keeps whatever it last saved, but we recompute analysts on
    read so widening the defaults (or fixing a misclassification) takes effect
    immediately without a manual re-add.
    """
    mode = row["mode"]
    return WatchlistEntry(
        symbol=row["symbol"],
        display_name=row["display_name"],
        mode=mode,
        interval_hours=row["interval_hours"],
        analysts=_analysts_for_mode(mode),
        use_tradingview=row["use_tradingview"],
        enabled=row["enabled"],
        last_analysis=row["last_analysis"],
        last_decision=row["last_decision"],
        last_signal=row["last_signal"],
    )


_DEFAULT_SEED = [
    # Gold — start here per user request
    ("XAUUSD", 0, True),
    # Major forex pairs
    ("BTCUSD", 0, True),
]


class Watchlist:
    """Read-through wrapper around the SQLite watchlist store."""

    def __init__(self):
        self._seed_if_empty()
        self._ensure_default_entries()

    def _seed_if_empty(self) -> None:
        if store.watchlist_count() > 0:
            return
        for symbol, hours, news in _DEFAULT_SEED:
            store.save_watchlist_entry(_make_entry(symbol, hours, news))

    def _ensure_default_entries(self) -> None:
        for symbol, hours, news in _DEFAULT_SEED:
            if self.get(symbol) is None:
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
            interval_seconds = 60 if entry.interval_hours <= 0 else entry.interval_hours * 3600
            if elapsed.total_seconds() >= interval_seconds:
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
        entries = []
        for e in self.all():
            # Recompute broker-derived fields at read time so older persisted
            # rows do not keep stale static classifications such as BTCUSD=forex.
            mode = detect_symbol_mode(e.symbol)
            use_tradingview = mode in ("forex", "commodity", "crypto", "index")
            entries.append(
                {
                    "symbol": e.symbol,
                    "display_name": get_symbol_display_name(e.symbol),
                    "mode": mode,
                    "interval_hours": e.interval_hours,
                    "interval_minutes": 1 if e.interval_hours <= 0 else e.interval_hours * 60,
                    "analysts": _analysts_for_mode(mode),
                    "use_tradingview": use_tradingview,
                    "enabled": e.enabled,
                    "last_analysis": e.last_analysis.isoformat() if e.last_analysis else None,
                    "last_decision": e.last_decision,
                    "last_signal": e.last_signal,
                }
            )
        return entries


# Global singleton — both processes import this, both hit the same SQLite file.
watchlist = Watchlist()
