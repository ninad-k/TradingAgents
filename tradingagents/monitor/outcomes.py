"""
Outcome evaluator: closes the loop between a decision and what actually
happened to the price afterwards.

Walks ledger rows whose ``horizon_hours`` has elapsed, fetches entry/exit
prices from the price-lookup helper, computes signed ``pnl_pct``, and
writes a row to ``decision_outcomes``. HOLD signals get ``pnl_pct = 0``
so we still record that the horizon passed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from tradingagents.monitor import store
from tradingagents.monitor.prices import get_close_at

logger = logging.getLogger(__name__)


_SIGNAL_SIGN = {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0}


def _signed_pnl_pct(signal: str, entry: float, exit_: float) -> Optional[float]:
    sign = _SIGNAL_SIGN.get(signal.upper())
    if sign is None or entry == 0:
        return None
    if sign == 0:
        return 0.0
    return ((exit_ - entry) / entry) * sign * 100.0


def evaluate_pending(now: Optional[datetime] = None, limit: int = 100) -> int:
    """Evaluate up to ``limit`` due decisions. Returns the count processed."""
    now = now or datetime.now()
    pending = store.unevaluated_decisions(now=now)
    if not pending:
        return 0

    processed = 0
    for decision in pending[:limit]:
        _evaluate_one(decision, now)
        processed += 1
    return processed


def _evaluate_one(decision: dict, now: datetime) -> None:
    decision_id = decision["id"]
    symbol = decision["symbol"]
    signal = decision["signal"]
    horizon_hours = int(decision["horizon_hours"])
    decided_at = datetime.fromisoformat(decision["decided_at"])
    exit_ts = decided_at + timedelta(hours=horizon_hours)

    if signal.upper() not in _SIGNAL_SIGN:
        store.save_outcome(
            decision_id=decision_id,
            entry_price=None,
            exit_price=None,
            pnl_pct=None,
            horizon_hours=horizon_hours,
            error=f"unknown signal: {signal!r}",
        )
        return

    entry = get_close_at(symbol, decided_at)
    exit_ = get_close_at(symbol, exit_ts)

    if entry is None or exit_ is None:
        store.save_outcome(
            decision_id=decision_id,
            entry_price=entry,
            exit_price=exit_,
            pnl_pct=None,
            horizon_hours=horizon_hours,
            error="price unavailable",
        )
        return

    pnl_pct = _signed_pnl_pct(signal, entry, exit_)
    store.save_outcome(
        decision_id=decision_id,
        entry_price=entry,
        exit_price=exit_,
        pnl_pct=pnl_pct,
        horizon_hours=horizon_hours,
        error=None,
    )
    logger.info(
        "Outcome: id=%s %s %s entry=%.5f exit=%.5f pnl=%.3f%%",
        decision_id, symbol, signal, entry, exit_, pnl_pct if pnl_pct is not None else 0,
    )
