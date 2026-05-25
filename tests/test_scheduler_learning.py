"""Tests for the confidence parser and learned-gate logic in the scheduler."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


# ─── _parse_confidence ────────────────────────────────────────────────────


def test_parse_confidence_decimal():
    from tradingagents.monitor.scheduler import _parse_confidence
    assert _parse_confidence("My confidence: 0.83") == pytest.approx(0.83)


def test_parse_confidence_percent():
    from tradingagents.monitor.scheduler import _parse_confidence
    assert _parse_confidence("Confidence 80%") == pytest.approx(0.80)


def test_parse_confidence_bolded_label():
    from tradingagents.monitor.scheduler import _parse_confidence
    assert _parse_confidence("**Confidence:** 65%") == pytest.approx(0.65)


def test_parse_confidence_integer_treated_as_pct():
    """A bare integer above 1.0 should be interpreted as a percent."""
    from tradingagents.monitor.scheduler import _parse_confidence
    assert _parse_confidence("confidence 70") == pytest.approx(0.70)


def test_parse_confidence_missing_returns_none():
    from tradingagents.monitor.scheduler import _parse_confidence
    assert _parse_confidence("no signal here") is None
    assert _parse_confidence(None) is None
    assert _parse_confidence("") is None


def test_parse_confidence_out_of_range_returns_none():
    from tradingagents.monitor.scheduler import _parse_confidence
    # 200 → percent path divides by 100 → 2.0, still > 1.0 → rejected.
    assert _parse_confidence("confidence 200") is None


# ─── _apply_learned_gates ─────────────────────────────────────────────────


def test_gate_passes_when_no_threshold_configured(isolated_store, monkeypatch):
    """If learned_params doesn't set a threshold, BUY/SELL passes through."""
    from tradingagents.monitor import scheduler, learning_config

    monkeypatch.setattr(learning_config, "load_learned_params",
                        lambda: {"hold_horizon_hours": 24})

    signal, text, reason = scheduler._apply_learned_gates(
        "BUY", "Confidence: 0.40 — go long."
    )
    assert signal == "BUY"
    assert reason is None
    assert text == "Confidence: 0.40 — go long."


def test_gate_demotes_buy_to_hold_below_threshold(isolated_store, monkeypatch):
    from tradingagents.monitor import scheduler, learning_config

    monkeypatch.setattr(learning_config, "load_learned_params",
                        lambda: {"signal_confidence_threshold": 0.7})

    signal, text, reason = scheduler._apply_learned_gates(
        "BUY", "Confidence: 0.55 — go long."
    )
    assert signal == "HOLD"
    assert reason is not None
    assert "0.55" in reason and "0.70" in reason
    assert "[learned-gate]" in text


def test_gate_passes_buy_at_or_above_threshold(isolated_store, monkeypatch):
    from tradingagents.monitor import scheduler, learning_config
    monkeypatch.setattr(learning_config, "load_learned_params",
                        lambda: {"signal_confidence_threshold": 0.7})
    signal, _, reason = scheduler._apply_learned_gates(
        "BUY", "Confidence 75% — clean breakout."
    )
    assert signal == "BUY"
    assert reason is None


def test_gate_skips_hold_signals(isolated_store, monkeypatch):
    from tradingagents.monitor import scheduler, learning_config
    monkeypatch.setattr(learning_config, "load_learned_params",
                        lambda: {"signal_confidence_threshold": 0.9})
    signal, _, reason = scheduler._apply_learned_gates(
        "HOLD", "Confidence: 0.20 — waiting."
    )
    assert signal == "HOLD"
    assert reason is None


def test_gate_skips_when_confidence_missing(isolated_store, monkeypatch):
    """No confidence string in decision text → cannot gate, signal passes."""
    from tradingagents.monitor import scheduler, learning_config
    monkeypatch.setattr(learning_config, "load_learned_params",
                        lambda: {"signal_confidence_threshold": 0.9})
    signal, _, reason = scheduler._apply_learned_gates(
        "SELL", "Strong bearish setup, short the rip."
    )
    assert signal == "SELL"
    assert reason is None
