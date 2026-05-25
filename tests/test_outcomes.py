"""Tests for the outcome evaluator's PnL math and the evaluate_pending walk."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pytest


pytestmark = pytest.mark.unit


def test_buy_pnl_positive_when_exit_above_entry():
    from tradingagents.monitor.outcomes import _signed_pnl_pct
    assert _signed_pnl_pct("BUY", 100.0, 110.0) == pytest.approx(10.0)


def test_buy_pnl_negative_when_exit_below_entry():
    from tradingagents.monitor.outcomes import _signed_pnl_pct
    assert _signed_pnl_pct("BUY", 100.0, 90.0) == pytest.approx(-10.0)


def test_sell_pnl_positive_when_exit_below_entry():
    from tradingagents.monitor.outcomes import _signed_pnl_pct
    # Short profits when price drops.
    assert _signed_pnl_pct("SELL", 100.0, 90.0) == pytest.approx(10.0)


def test_sell_pnl_negative_when_exit_above_entry():
    from tradingagents.monitor.outcomes import _signed_pnl_pct
    assert _signed_pnl_pct("SELL", 100.0, 110.0) == pytest.approx(-10.0)


def test_hold_pnl_always_zero():
    from tradingagents.monitor.outcomes import _signed_pnl_pct
    assert _signed_pnl_pct("HOLD", 100.0, 999.0) == 0.0
    assert _signed_pnl_pct("HOLD", 100.0, 1.0) == 0.0


def test_pnl_returns_none_on_zero_entry():
    from tradingagents.monitor.outcomes import _signed_pnl_pct
    assert _signed_pnl_pct("BUY", 0.0, 5.0) is None


def test_pnl_returns_none_on_unknown_signal():
    from tradingagents.monitor.outcomes import _signed_pnl_pct
    assert _signed_pnl_pct("WAT", 100.0, 110.0) is None


def _seed_pending_decision(store, signal: str, hours_ago: int = 25, horizon: int = 24) -> int:
    return store.record_decision(
        symbol="XAUUSD",
        signal=signal,
        decision_text=f"{signal} gold",
        success=True,
        horizon_hours=horizon,
        decided_at=datetime.now() - timedelta(hours=hours_ago),
    )


def test_evaluate_pending_writes_outcome_with_prices(isolated_store, monkeypatch):
    from tradingagents.monitor import outcomes, store

    did = _seed_pending_decision(store, "BUY")

    prices = iter([2000.0, 2040.0])  # entry then exit
    def _fake_close(sym: str, ts: datetime) -> Optional[float]:
        return next(prices)
    monkeypatch.setattr(outcomes, "get_close_at", _fake_close)

    n = outcomes.evaluate_pending()
    assert n == 1

    rows = store.recent_decisions_with_outcomes()
    assert rows[0]["id"] == did
    assert rows[0]["entry_price"] == 2000.0
    assert rows[0]["exit_price"] == 2040.0
    assert rows[0]["pnl_pct"] == pytest.approx(2.0)


def test_evaluate_pending_records_error_on_missing_price(isolated_store, monkeypatch):
    from tradingagents.monitor import outcomes, store

    _seed_pending_decision(store, "BUY")
    monkeypatch.setattr(outcomes, "get_close_at", lambda *a, **kw: None)

    n = outcomes.evaluate_pending()
    assert n == 1

    row = store.recent_decisions_with_outcomes()[0]
    assert row["pnl_pct"] is None
    assert row["outcome_error"] == "price unavailable"


def test_evaluate_pending_handles_hold(isolated_store, monkeypatch):
    from tradingagents.monitor import outcomes, store

    _seed_pending_decision(store, "HOLD")
    monkeypatch.setattr(outcomes, "get_close_at", lambda *a, **kw: 100.0)

    outcomes.evaluate_pending()
    row = store.recent_decisions_with_outcomes()[0]
    assert row["pnl_pct"] == 0.0


def test_evaluate_pending_unknown_signal_records_error(isolated_store, monkeypatch):
    from tradingagents.monitor import outcomes, store

    store.record_decision(
        symbol="XAUUSD", signal="WAT", decision_text="?", success=True,
        horizon_hours=24, decided_at=datetime.now() - timedelta(hours=25),
    )
    monkeypatch.setattr(outcomes, "get_close_at", lambda *a, **kw: 100.0)

    outcomes.evaluate_pending()
    row = store.recent_decisions_with_outcomes()[0]
    assert row["pnl_pct"] is None
    assert "unknown signal" in (row["outcome_error"] or "")


def test_evaluate_pending_empty_returns_zero(isolated_store):
    from tradingagents.monitor import outcomes
    assert outcomes.evaluate_pending() == 0
