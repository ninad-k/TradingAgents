"""Tests for reviewer's scoreboard, JSON extraction, and validation rules."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest


pytestmark = pytest.mark.unit


def _seed_evaluated_decision(store, signal: str, pnl_pct: float, *, hours_ago: int = 48):
    did = store.record_decision(
        symbol="XAUUSD",
        signal=signal,
        decision_text=f"{signal} XAUUSD",
        success=True,
        horizon_hours=24,
        decided_at=datetime.now() - timedelta(hours=hours_ago),
    )
    # entry/exit kept simple: pnl_pct is what build_scoreboard reads.
    store.save_outcome(
        decision_id=did, entry_price=100.0,
        exit_price=100.0 * (1 + pnl_pct / 100.0),
        pnl_pct=pnl_pct, horizon_hours=24,
    )
    return did


def test_scoreboard_empty_window(isolated_store):
    from tradingagents.monitor import reviewer
    sb = reviewer.build_scoreboard(window_days=30)
    assert sb.n_decisions == 0
    assert sb.n_evaluated == 0
    assert sb.win_rate is None
    assert sb.mean_pnl_pct is None


def test_scoreboard_aggregates_pnl(isolated_store):
    from tradingagents.monitor import reviewer, store

    for signal, pnl in [("BUY", 2.0), ("BUY", -1.0), ("SELL", 3.0), ("SELL", -0.5)]:
        _seed_evaluated_decision(store, signal, pnl)

    sb = reviewer.build_scoreboard(window_days=30)
    assert sb.n_evaluated == 4
    assert sb.win_rate == pytest.approx(0.5)
    assert sb.mean_pnl_pct == pytest.approx(0.875)
    assert sb.total_return_pct == pytest.approx(3.5)
    assert sb.per_signal["BUY"]["count"] == 2
    assert sb.per_signal["SELL"]["count"] == 2


def test_scoreboard_drawdown_tracks_peak(isolated_store):
    from tradingagents.monitor import reviewer, store

    # Cumulative: +5, +5+(-3)=2 (peak=5, dd=-3), +2-2=0 (dd=-5)
    for signal, pnl, hours_ago in [
        ("BUY", 5.0, 60), ("BUY", -3.0, 48), ("BUY", -2.0, 36),
    ]:
        _seed_evaluated_decision(store, signal, pnl, hours_ago=hours_ago)

    sb = reviewer.build_scoreboard(window_days=30)
    assert sb.max_drawdown_pct == pytest.approx(-5.0)


def test_extract_json_handles_clean_blob():
    from tradingagents.monitor.reviewer import _extract_json
    raw = '{"key": "x", "old": 1, "new": 2, "rationale": "ok"}'
    assert _extract_json(raw) == {"key": "x", "old": 1, "new": 2, "rationale": "ok"}


def test_extract_json_handles_prose_wrap():
    from tradingagents.monitor.reviewer import _extract_json
    raw = (
        "Sure! Here's my proposal:\n"
        '{"key": "x", "old": 1, "new": 2, "rationale": "win rate low"}\n'
        "Hope this helps."
    )
    parsed = _extract_json(raw)
    assert parsed["key"] == "x" and parsed["new"] == 2


def test_extract_json_returns_none_on_malformed():
    from tradingagents.monitor.reviewer import _extract_json
    assert _extract_json("no json here at all") is None
    assert _extract_json("") is None


def test_validate_delta_rejects_unknown_key():
    from tradingagents.monitor.reviewer import _validate_delta
    current = {"signal_confidence_threshold": 0.6}
    proposal = {"key": "nonexistent", "old": 0, "new": 1, "rationale": "x"}
    out, err = _validate_delta(proposal, current)
    assert out is None and "unknown key" in err


def test_validate_delta_rejects_type_mismatch():
    from tradingagents.monitor.reviewer import _validate_delta
    current = {"signal_confidence_threshold": 0.6}
    proposal = {"key": "signal_confidence_threshold", "old": 0.6, "new": "high", "rationale": "x"}
    out, err = _validate_delta(proposal, current)
    assert out is None and "type mismatch" in err


def test_validate_delta_rejects_noop():
    from tradingagents.monitor.reviewer import _validate_delta
    current = {"signal_confidence_threshold": 0.6}
    proposal = {"key": "signal_confidence_threshold", "old": 0.6, "new": 0.6, "rationale": "x"}
    out, err = _validate_delta(proposal, current)
    assert out is None and err == "proposal is a no-op"


def test_validate_delta_rejects_missing_new():
    from tradingagents.monitor.reviewer import _validate_delta
    current = {"k": 1}
    out, err = _validate_delta({"key": "k", "old": 1}, current)
    assert out is None and "missing 'new'" in err


def test_validate_delta_handles_null_key_declined():
    from tradingagents.monitor.reviewer import _validate_delta
    current = {"k": 1}
    out, err = _validate_delta({"key": None, "rationale": "insufficient evidence"}, current)
    assert out is None and "insufficient evidence" in err


def test_validate_delta_accepts_valid():
    from tradingagents.monitor.reviewer import _validate_delta
    current = {"signal_confidence_threshold": 0.6}
    proposal = {
        "key": "signal_confidence_threshold", "old": 0.6, "new": 0.7,
        "rationale": "win rate trending up",
    }
    out, err = _validate_delta(proposal, current)
    assert err is None
    assert out == {"key": "signal_confidence_threshold", "old": 0.6, "new": 0.7,
                   "rationale": "win rate trending up"}


def test_run_review_writes_proposal_when_evidence_sufficient(isolated_store, monkeypatch):
    """End-to-end: seed enough evaluated decisions, mock the LLM, verify the proposal lands."""
    from tradingagents.monitor import reviewer, store

    # Goals require min_decisions_for_review = 20 by default; seed 22.
    for i in range(22):
        _seed_evaluated_decision(store, "BUY" if i % 2 else "SELL", -1.0 - (i * 0.05))

    # Stub LLM call to return a valid proposal.
    def _stub_llm(prompt: str) -> str:
        return json.dumps({
            "key": "signal_confidence_threshold", "old": 0.6, "new": 0.75,
            "rationale": "win rate trending down, tighten gate",
        })
    monkeypatch.setattr(reviewer, "_ask_llm_for_delta", _stub_llm)

    # Force PROPOSALS_DIR to the isolated tmp path the env var set.
    import os
    from pathlib import Path
    monkeypatch.setattr(reviewer, "PROPOSALS_DIR", Path(os.environ["TRADINGAGENTS_PROPOSALS_DIR"]))

    result = reviewer.run_review(auto_apply=False)
    assert result.proposal is not None
    assert result.proposal["key"] == "signal_confidence_threshold"
    assert result.applied is False
    assert result.proposal_path is not None and result.proposal_path.exists()

    pending = store.pending_proposals()
    assert len(pending) == 1


def test_run_review_skips_when_insufficient_data(isolated_store, monkeypatch):
    from tradingagents.monitor import reviewer
    from pathlib import Path
    import os
    monkeypatch.setattr(reviewer, "PROPOSALS_DIR", Path(os.environ["TRADINGAGENTS_PROPOSALS_DIR"]))

    # No decisions seeded → insufficient data.
    result = reviewer.run_review(auto_apply=False)
    assert result.proposal is None
    assert result.rejection_reason == "insufficient data"
    # The skip path still writes a markdown summary for auditability.
    assert result.proposal_path is not None and result.proposal_path.exists()
