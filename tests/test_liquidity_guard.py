"""Deterministic liquidity scanner + hard trade gate."""

import pandas as pd
import pytest

from tradingagents.analytics.liquidity import (
    LiquidityMap,
    LiquiditySweep,
    TimeframeScan,
    classify_structure,
    find_pools,
    find_recent_sweep,
    find_swings,
    qualify_liquidity_setup,
    scan_dataframe,
)


def _bars(rows):
    """rows: list of (high, low, close). open synthesized; time = index."""
    return pd.DataFrame(
        {
            "time": range(len(rows)),
            "open": [r[2] for r in rows],
            "high": [r[0] for r in rows],
            "low": [r[1] for r in rows],
            "close": [r[2] for r in rows],
        }
    )


def _flat(n, level=100.0, wiggle=0.5):
    return [(level + wiggle, level - wiggle, level)] * n


def test_find_swings_detects_fractal_pivots():
    highs = [1, 2, 5, 2, 1, 2, 6, 2, 1]
    lows = [1, 0.5, 1, 0.4, 1, 0.6, 1, 0.3, 1]
    swing_highs, swing_lows = find_swings(highs, lows, k=2)
    assert 2 in swing_highs and 6 in swing_highs
    assert 3 in swing_lows


def test_find_pools_clusters_equal_levels():
    lows = [100.0, 99.98, 100.01, 90.0]
    pools = find_pools(lows, [0, 1, 2, 3], tolerance=0.05, side="sell_side")
    equal_lows = [p for p in pools if p.touches >= 2]
    assert len(equal_lows) == 1
    assert equal_lows[0].level == pytest.approx(99.98)
    # The lone 90.0 low is not a pool (single touch).
    assert all(p.touches >= 2 for p in equal_lows)


def test_sell_side_sweep_is_bullish():
    # Two equal lows at ~95, then a bar wicks to 94 but closes back at 96.
    rows = _flat(30)
    rows[10] = (100.5, 95.0, 100.0)
    rows[16] = (100.5, 95.02, 100.0)
    rows[27] = (100.5, 94.0, 96.0)  # the sweep bar
    df = _bars(rows)
    scan = scan_dataframe(df, "M5", sweep_max_age_bars=20)
    assert scan.recent_sweep is not None
    assert scan.recent_sweep.side == "sell_side"
    assert scan.recent_sweep.bias == "bullish"
    assert scan.recent_sweep.bars_ago == 2


def test_buy_side_sweep_is_bearish():
    rows = _flat(30)
    rows[8] = (105.0, 99.5, 100.0)
    rows[15] = (105.03, 99.5, 100.0)
    rows[27] = (106.0, 99.5, 104.0)  # wick above equal highs, close back below
    df = _bars(rows)
    scan = scan_dataframe(df, "M5", sweep_max_age_bars=20)
    assert scan.recent_sweep is not None
    assert scan.recent_sweep.side == "buy_side"
    assert scan.recent_sweep.bias == "bearish"


def test_structure_classification():
    assert classify_structure([1, 2], [1, 2], [0, 1], [0, 1]) == "bullish"
    assert classify_structure([2, 1], [2, 1], [0, 1], [0, 1]) == "bearish"
    assert classify_structure([1, 2], [2, 1], [0, 1], [0, 1]) == "range"
    assert classify_structure([1], [1], [0], [0]) == "unknown"


# ─── qualify_liquidity_setup (the hard gate) ────────────────────────────────


def _scan(tf, structure="range", zone="equilibrium", sweep=None, error=None):
    return TimeframeScan(
        timeframe=tf, bars=200, last_close=100.0, bar_time="", atr=1.0,
        structure=structure, zone=zone, recent_sweep=sweep, error=error,
    )


def _sweep(bias, bars_ago=3):
    side = "sell_side" if bias == "bullish" else "buy_side"
    return LiquiditySweep(side=side, bias=bias, level=99.0, bars_ago=bars_ago, bar_time="")


def _map(**scans):
    lmap = LiquidityMap(symbol="TEST", generated_at="now")
    lmap.scans = scans
    return lmap


def test_buy_qualifies_with_sweep_and_aligned_structure():
    lmap = _map(
        M1=_scan("M1", sweep=_sweep("bullish")),
        M5=_scan("M5"),
        M15=_scan("M15"),
        H1=_scan("H1", structure="bullish"),
        H4=_scan("H4", structure="range"),
    )
    ok, reason = qualify_liquidity_setup(lmap, "BUY")
    assert ok, reason
    assert "sell_side sweep on M1" in reason


def test_buy_blocked_without_sweep():
    lmap = _map(
        M1=_scan("M1"), M5=_scan("M5"), M15=_scan("M15"),
        H1=_scan("H1", structure="bullish"), H4=_scan("H4"),
    )
    ok, reason = qualify_liquidity_setup(lmap, "BUY")
    assert not ok
    assert "no recent sell-side liquidity sweep" in reason


def test_buy_blocked_against_uniform_bearish_structure():
    lmap = _map(
        M1=_scan("M1", sweep=_sweep("bullish")),
        M5=_scan("M5"), M15=_scan("M15"),
        H1=_scan("H1", structure="bearish"),
        H4=_scan("H4", structure="bearish"),
    )
    ok, reason = qualify_liquidity_setup(lmap, "BUY")
    assert not ok
    assert "uniformly bearish" in reason


def test_buy_blocked_in_premium_zone():
    lmap = _map(
        M1=_scan("M1", sweep=_sweep("bullish")),
        M5=_scan("M5"), M15=_scan("M15"),
        H1=_scan("H1", structure="bullish", zone="premium"),
        H4=_scan("H4"),
    )
    ok, reason = qualify_liquidity_setup(lmap, "BUY")
    assert not ok
    assert "premium" in reason


def test_sell_mirror_rules():
    lmap = _map(
        M1=_scan("M1", sweep=_sweep("bearish")),
        M5=_scan("M5"), M15=_scan("M15"),
        H1=_scan("H1", structure="bearish"),
        H4=_scan("H4", structure="range"),
    )
    ok, reason = qualify_liquidity_setup(lmap, "SELL")
    assert ok, reason


def test_fails_closed_when_lower_timeframes_unavailable():
    lmap = _map(
        M1=_scan("M1", error="no data"),
        M5=_scan("M5", error="no data"),
        M15=_scan("M15", error="no data"),
        H1=_scan("H1", structure="bullish"),
        H4=_scan("H4"),
    )
    ok, reason = qualify_liquidity_setup(lmap, "BUY")
    assert not ok
    assert "failing closed" in reason


def test_fails_closed_when_higher_timeframes_unavailable():
    lmap = _map(
        M1=_scan("M1", sweep=_sweep("bullish")),
        M5=_scan("M5"), M15=_scan("M15"),
        H1=_scan("H1", error="no data"),
        H4=_scan("H4", error="no data"),
    )
    ok, reason = qualify_liquidity_setup(lmap, "BUY")
    assert not ok
    assert "failing closed" in reason


def test_hold_never_qualifies():
    lmap = _map(M1=_scan("M1", sweep=_sweep("bullish")), H1=_scan("H1"), H4=_scan("H4"))
    ok, _ = qualify_liquidity_setup(lmap, "HOLD")
    assert not ok


def test_stale_sweep_does_not_qualify():
    lmap = _map(
        M1=_scan("M1", sweep=_sweep("bullish", bars_ago=50)),
        M5=_scan("M5"), M15=_scan("M15"),
        H1=_scan("H1", structure="bullish"), H4=_scan("H4"),
    )
    ok, reason = qualify_liquidity_setup(lmap, "BUY", sweep_max_age_bars=20)
    assert not ok


def test_markdown_rendering_includes_computed_disclaimer():
    lmap = _map(M1=_scan("M1", sweep=_sweep("bullish")), H1=_scan("H1"))
    md = lmap.to_markdown()
    assert "computed, not model-generated" in md
    assert "TEST" in md
