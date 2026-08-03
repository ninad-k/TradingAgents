"""Reviewer proposal-key normalization (anti-hallucination guard)."""

from tradingagents.monitor.reviewer import _normalize_key, _validate_delta

PARAMS = {
    "signal_confidence_threshold": 0.5,
    "hold_horizon_hours": 24,
    "news_weight": 1.0,
}


def test_exact_key_passes_through():
    assert _normalize_key("hold_horizon_hours", PARAMS) == "hold_horizon_hours"


def test_observed_hallucination_is_normalized():
    # This exact near-miss was produced live by the reviewer LLM.
    assert _normalize_key("confidence_threshold", PARAMS) == "signal_confidence_threshold"


def test_unmatched_key_rejected():
    assert _normalize_key("max_leverage", PARAMS) is None


def test_ambiguous_key_rejected():
    params = {"a_weight": 1.0, "b_weight": 2.0}
    assert _normalize_key("weight", params) is None


def test_validate_delta_uses_normalized_key():
    proposal = {"key": "confidence_threshold", "old": 0.5, "new": 0.6}
    delta, reason = _validate_delta(proposal, PARAMS)
    assert reason is None
    assert delta["key"] == "signal_confidence_threshold"


def test_validate_delta_still_rejects_unknown():
    proposal = {"key": "made_up_param", "new": 1}
    delta, reason = _validate_delta(proposal, PARAMS)
    assert delta is None
    assert "unknown key" in reason
