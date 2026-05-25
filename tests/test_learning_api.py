"""Integration tests for /api/learning/* — seed store, drive the API, check effects."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest


pytestmark = pytest.mark.integration


@pytest.fixture()
def client(isolated_store, monkeypatch):
    """A TestClient wired against the isolated store, with reviewer dirs patched."""
    from fastapi.testclient import TestClient
    from pathlib import Path
    import os
    # PROPOSALS_DIR is module-level on reviewer, so patch the attribute too.
    from tradingagents.monitor import reviewer
    monkeypatch.setattr(reviewer, "PROPOSALS_DIR", Path(os.environ["TRADINGAGENTS_PROPOSALS_DIR"]))

    from tradingagents.api.dashboard_api import app
    with TestClient(app) as c:
        yield c


def _seed_decision_with_outcome(store, signal: str = "BUY", pnl_pct: float = 1.5) -> int:
    did = store.record_decision(
        symbol="XAUUSD", signal=signal, decision_text=f"{signal} gold",
        success=True, horizon_hours=24,
        decided_at=datetime.now() - timedelta(hours=25),
    )
    store.save_outcome(
        decision_id=did, entry_price=2000.0, exit_price=2030.0,
        pnl_pct=pnl_pct, horizon_hours=24,
    )
    return did


def test_scoreboard_returns_zero_state_for_empty_store(client):
    resp = client.get("/api/learning/scoreboard?window_days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_decisions"] == 0
    assert body["win_rate"] is None


def test_scoreboard_reflects_seeded_decisions(client):
    from tradingagents.monitor import store
    _seed_decision_with_outcome(store, "BUY", 1.5)
    _seed_decision_with_outcome(store, "SELL", -0.5)
    resp = client.get("/api/learning/scoreboard?window_days=30")
    body = resp.json()
    assert body["n_evaluated"] == 2
    assert body["win_rate"] == pytest.approx(0.5)


def test_decisions_endpoint_filters_by_symbol(client):
    from tradingagents.monitor import store
    _seed_decision_with_outcome(store, "BUY")
    store.record_decision(
        symbol="EURUSD", signal="BUY", decision_text="long eur",
        success=True, horizon_hours=24, decided_at=datetime.now(),
    )
    resp = client.get("/api/learning/decisions?symbol=XAUUSD&limit=10")
    body = resp.json()
    assert all(r["symbol"] == "XAUUSD" for r in body)
    assert len(body) == 1


def test_decisions_endpoint_rejects_bad_since(client):
    resp = client.get("/api/learning/decisions?since=notadate")
    assert resp.status_code == 400


def test_proposals_list_filters_by_status(client):
    from tradingagents.monitor import store
    p1 = store.record_params_proposal({"signal_confidence_threshold": 0.7}, None, "raise")
    p2 = store.record_params_proposal({"signal_confidence_threshold": 0.8}, None, "raise more")
    store.apply_proposal(p2)

    pending = client.get("/api/learning/proposals?status=pending").json()
    assert [p["id"] for p in pending] == [p1]

    applied = client.get("/api/learning/proposals?status=applied").json()
    assert [p["id"] for p in applied] == [p2]


def test_proposals_list_rejects_bad_status(client):
    assert client.get("/api/learning/proposals?status=wat").status_code == 400


def test_proposal_get_returns_404_for_missing(client):
    assert client.get("/api/learning/proposals/9999").status_code == 404


def test_approve_proposal_writes_learned_params(client):
    from tradingagents.monitor import store, learning_config
    pid = store.record_params_proposal(
        params={"signal_confidence_threshold": 0.85, "hold_horizon_hours": 24},
        diff={"signal_confidence_threshold": {"from": 0.7, "to": 0.85}},
        rationale="win rate climbing",
    )

    resp = client.post(f"/api/learning/proposals/{pid}/approve")
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True
    assert body["params"]["signal_confidence_threshold"] == 0.85

    # Mutation visible on disk.
    on_disk = json.loads(learning_config.learned_params_path().read_text())
    assert on_disk["signal_confidence_threshold"] == 0.85

    # GET via the params endpoint matches.
    params_resp = client.get("/api/learning/params").json()
    assert params_resp["signal_confidence_threshold"] == 0.85


def test_approve_twice_is_409(client):
    from tradingagents.monitor import store
    pid = store.record_params_proposal({"signal_confidence_threshold": 0.7}, None, "n/a")
    assert client.post(f"/api/learning/proposals/{pid}/approve").status_code == 200
    assert client.post(f"/api/learning/proposals/{pid}/approve").status_code == 409


def test_reject_proposal_records_reason(client):
    from tradingagents.monitor import store
    pid = store.record_params_proposal({"signal_confidence_threshold": 0.7}, None, "n/a")
    resp = client.post(
        f"/api/learning/proposals/{pid}/reject", json={"reason": "too aggressive"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["proposal"]["rejection_reason"] == "too aggressive"

    # Approve after reject is 409.
    assert client.post(f"/api/learning/proposals/{pid}/approve").status_code == 409


def test_goals_endpoint_serves_loaded_goals(client):
    resp = client.get("/api/learning/goals")
    assert resp.status_code == 200
    body = resp.json()
    # The defaults shipped with the package must include at least review_window_days.
    assert "review_window_days" in body
