"""Tests for the learning-loop slice of tradingagents.monitor.store."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


pytestmark = pytest.mark.unit


def _import_store():
    from tradingagents.monitor import store
    return store


def test_idempotent_migration(isolated_store):
    """Re-running schema init must not error on existing columns."""
    store = _import_store()
    # Triggers init once via any helper.
    store.list_proposals()
    # Clear the init guard and trigger again — _migrate_proposal_lifecycle
    # must swallow the duplicate-column error.
    store._INITIALISED_PATHS.clear()
    store.list_proposals()


def test_record_decision_and_unevaluated_window(isolated_store):
    store = _import_store()
    now = datetime.now()
    # Backdated 25h: outside a 24h horizon → unevaluated.
    past_id = store.record_decision(
        symbol="XAUUSD",
        signal="BUY",
        decision_text="long gold",
        success=True,
        horizon_hours=24,
        decided_at=now - timedelta(hours=25),
    )
    # Just decided: within horizon → not yet due.
    store.record_decision(
        symbol="XAUUSD",
        signal="SELL",
        decision_text="short gold",
        success=True,
        horizon_hours=24,
        decided_at=now,
    )
    pending = store.unevaluated_decisions(now=now)
    assert [p["id"] for p in pending] == [past_id]


def test_failed_decisions_excluded_from_unevaluated(isolated_store):
    store = _import_store()
    now = datetime.now()
    store.record_decision(
        symbol="EURUSD", signal="BUY", decision_text=None, success=False,
        horizon_hours=1, decided_at=now - timedelta(hours=2), error="boom",
    )
    assert store.unevaluated_decisions(now=now) == []


def test_save_outcome_joins_into_recent(isolated_store):
    store = _import_store()
    now = datetime.now()
    did = store.record_decision(
        symbol="NVDA", signal="BUY", decision_text="ai", success=True,
        horizon_hours=24, decided_at=now - timedelta(hours=25),
    )
    store.save_outcome(
        decision_id=did, entry_price=100.0, exit_price=102.0,
        pnl_pct=2.0, horizon_hours=24,
    )
    rows = store.recent_decisions_with_outcomes()
    assert len(rows) == 1
    assert rows[0]["entry_price"] == 100.0
    assert rows[0]["exit_price"] == 102.0
    assert rows[0]["pnl_pct"] == 2.0


def test_proposal_history_orders_newest_first(isolated_store):
    store = _import_store()
    a = store.record_params_proposal({"k": 1}, None, "first")
    b = store.record_params_proposal({"k": 2}, None, "second")
    rows = store.list_proposals(limit=10)
    assert [r["id"] for r in rows] == [b, a]


def test_pending_proposals_filters_applied_and_rejected(isolated_store):
    store = _import_store()
    a = store.record_params_proposal({"signal_confidence_threshold": 0.7}, None, "raise")
    b = store.record_params_proposal({"signal_confidence_threshold": 0.8}, None, "raise more")
    c = store.record_params_proposal({"signal_confidence_threshold": 0.9}, None, "even more")

    store.reject_proposal(a, "too aggressive")
    store.apply_proposal(b)

    pending_ids = [p["id"] for p in store.pending_proposals()]
    assert pending_ids == [c]

    assert [p["id"] for p in store.list_proposals(status="applied")] == [b]
    assert [p["id"] for p in store.list_proposals(status="rejected")] == [a]


def test_apply_proposal_writes_learned_params_file(isolated_store):
    """apply_proposal must mutate the on-disk learned_params.json atomically."""
    import json
    store = _import_store()
    from tradingagents.monitor import learning_config

    pid = store.record_params_proposal(
        params={"signal_confidence_threshold": 0.75, "hold_horizon_hours": 24},
        diff={"signal_confidence_threshold": {"from": 0.6, "to": 0.75}},
        rationale="bump threshold",
    )
    new_params = store.apply_proposal(pid)
    assert new_params["signal_confidence_threshold"] == 0.75

    on_disk = json.loads(learning_config.learned_params_path().read_text())
    assert on_disk["signal_confidence_threshold"] == 0.75

    refreshed = store.get_proposal(pid)
    assert refreshed["applied"] is True
    assert refreshed["applied_at"] is not None


def test_apply_then_reject_raises(isolated_store):
    store = _import_store()
    pid = store.record_params_proposal({"signal_confidence_threshold": 0.7}, None, "n/a")
    store.apply_proposal(pid)
    with pytest.raises(store.ProposalAlreadyResolved):
        store.reject_proposal(pid, "second thoughts")


def test_reject_then_apply_raises(isolated_store):
    store = _import_store()
    pid = store.record_params_proposal({"signal_confidence_threshold": 0.7}, None, "n/a")
    store.reject_proposal(pid, "noisy")
    with pytest.raises(store.ProposalAlreadyResolved):
        store.apply_proposal(pid)


def test_apply_missing_proposal_raises(isolated_store):
    store = _import_store()
    with pytest.raises(store.ProposalNotFound):
        store.apply_proposal(9999)
