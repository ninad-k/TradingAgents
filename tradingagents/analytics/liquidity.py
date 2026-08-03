"""Multi-timeframe liquidity / market-structure scanner.

Everything in this module is DETERMINISTIC — computed from broker OHLC bars,
never from LLM output. It powers two things:

1. The ``get_liquidity_map`` agent tool, so the Market Analyst can ground its
   narrative in real, computed structure instead of hallucinating levels.
2. The hard pre-execution gate in the scheduler: no BUY/SELL order is placed
   unless :func:`qualify_liquidity_setup` confirms a qualifying pattern
   (liquidity sweep + structure alignment) on real data. Missing data fails
   closed — no data, no trade.

Concepts implemented (standard "smart money" liquidity concepts):

- Swing highs/lows (fractal pivots).
- Liquidity pools: clusters of equal highs (buy-side liquidity above) and
  equal lows (sell-side liquidity below), where resting stops accumulate.
- Liquidity sweep: a bar that wicks through a pool level but closes back on
  the original side — the classic stop-hunt/reversal fingerprint. A sweep of
  sell-side liquidity (below equal lows) is a bullish signal; a sweep of
  buy-side liquidity (above equal highs) is bearish.
- Market structure: higher-highs/higher-lows (bullish), lower-highs/lower-lows
  (bearish), otherwise range.
- Premium/discount: where price sits inside the recent range (above 62% =
  premium, below 38% = discount).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Timeframes scanned, lower → higher, with bar counts per fetch.
TIMEFRAME_BARS: Dict[str, int] = {
    "M1": 400,
    "M5": 300,
    "M15": 250,
    "H1": 250,
    "H4": 200,
    "D1": 200,
}

LOWER_TIMEFRAMES: Tuple[str, ...] = ("M1", "M5", "M15")
HIGHER_TIMEFRAMES: Tuple[str, ...] = ("H1", "H4")

# Fractal pivot half-window: a swing high is strictly the highest of its
# k neighbours on each side.
SWING_K = 2
# Two swing points within this many ATRs of each other count as "equal"
# (a liquidity pool).
POOL_ATR_TOLERANCE = 0.25
# A pool needs at least this many touches to hold meaningful liquidity.
MIN_POOL_TOUCHES = 2
# Range position thresholds for premium/discount.
PREMIUM_ABOVE = 0.62
DISCOUNT_BELOW = 0.38


@dataclass(frozen=True)
class LiquidityPool:
    side: str            # "buy_side" (above equal highs) | "sell_side" (below equal lows)
    level: float
    touches: int
    last_touch_index: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiquiditySweep:
    side: str            # "sell_side" swept -> bullish; "buy_side" swept -> bearish
    bias: str            # "bullish" | "bearish"
    level: float
    bars_ago: int
    bar_time: str        # ISO timestamp of the sweep bar

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TimeframeScan:
    timeframe: str
    bars: int
    last_close: float
    bar_time: str
    atr: float
    structure: str               # "bullish" | "bearish" | "range" | "unknown"
    zone: str                    # "premium" | "discount" | "equilibrium"
    buy_side_pools: List[LiquidityPool] = field(default_factory=list)
    sell_side_pools: List[LiquidityPool] = field(default_factory=list)
    recent_sweep: Optional[LiquiditySweep] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "bars": self.bars,
            "last_close": self.last_close,
            "bar_time": self.bar_time,
            "atr": self.atr,
            "structure": self.structure,
            "zone": self.zone,
            "buy_side_pools": [p.to_dict() for p in self.buy_side_pools],
            "sell_side_pools": [p.to_dict() for p in self.sell_side_pools],
            "recent_sweep": self.recent_sweep.to_dict() if self.recent_sweep else None,
            "error": self.error,
        }


@dataclass
class LiquidityMap:
    symbol: str
    generated_at: str
    scans: Dict[str, TimeframeScan] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "generated_at": self.generated_at,
            "scans": {tf: scan.to_dict() for tf, scan in self.scans.items()},
        }

    def to_markdown(self) -> str:
        """Human/LLM-readable rendering of the computed map."""
        lines = [
            f"### Liquidity Map — {self.symbol} (computed from broker data at {self.generated_at})",
            "",
            "| TF | Structure | Zone | Buy-side pools (above) | Sell-side pools (below) | Recent sweep |",
            "|---|---|---|---|---|---|",
        ]
        for tf in TIMEFRAME_BARS:
            scan = self.scans.get(tf)
            if scan is None:
                continue
            if scan.error:
                lines.append(f"| {tf} | — | — | — | — | unavailable: {scan.error} |")
                continue
            bsp = ", ".join(f"{p.level:g}×{p.touches}" for p in scan.buy_side_pools[:3]) or "none"
            ssp = ", ".join(f"{p.level:g}×{p.touches}" for p in scan.sell_side_pools[:3]) or "none"
            sweep = "none"
            if scan.recent_sweep:
                s = scan.recent_sweep
                sweep = f"{s.side} swept @ {s.level:g}, {s.bars_ago} bars ago → {s.bias}"
            lines.append(
                f"| {tf} | {scan.structure} | {scan.zone} | {bsp} | {ssp} | {sweep} |"
            )
        lines.append("")
        lines.append(
            "_Pools are clusters of equal highs/lows (resting liquidity). A sweep is a "
            "wick through a pool that closes back inside — sell-side sweeps are bullish, "
            "buy-side sweeps are bearish. This table is computed, not model-generated._"
        )
        return "\n".join(lines)


# ─── Pure detection functions (DataFrame in, facts out) ─────────────────────


def find_swings(highs: Sequence[float], lows: Sequence[float], k: int = SWING_K):
    """Return (swing_high_idx, swing_low_idx) lists of fractal pivot indices."""
    n = len(highs)
    swing_highs: List[int] = []
    swing_lows: List[int] = []
    for i in range(k, n - k):
        window_h = [highs[j] for j in range(i - k, i + k + 1) if j != i]
        window_l = [lows[j] for j in range(i - k, i + k + 1) if j != i]
        if highs[i] > max(window_h):
            swing_highs.append(i)
        if lows[i] < min(window_l):
            swing_lows.append(i)
    return swing_highs, swing_lows


def find_pools(
    prices: Sequence[float],
    indices: Sequence[int],
    tolerance: float,
    side: str,
) -> List[LiquidityPool]:
    """Cluster swing prices within ``tolerance`` into liquidity pools."""
    points = sorted(((prices[i], i) for i in indices), key=lambda x: x[0])
    pools: List[LiquidityPool] = []
    cluster: List[Tuple[float, int]] = []

    def flush() -> None:
        if len(cluster) >= MIN_POOL_TOUCHES:
            levels = [p for p, _ in cluster]
            level = max(levels) if side == "buy_side" else min(levels)
            pools.append(
                LiquidityPool(
                    side=side,
                    level=float(level),
                    touches=len(cluster),
                    last_touch_index=max(i for _, i in cluster),
                )
            )

    for point in points:
        if cluster and abs(point[0] - cluster[-1][0]) > tolerance:
            flush()
            cluster = []
        cluster.append(point)
    flush()
    # Most-recently-touched pools first.
    pools.sort(key=lambda p: p.last_touch_index, reverse=True)
    return pools


def find_recent_sweep(
    df,
    buy_side_pools: List[LiquidityPool],
    sell_side_pools: List[LiquidityPool],
    max_age_bars: int,
) -> Optional[LiquiditySweep]:
    """Most recent liquidity sweep of any pool within ``max_age_bars``.

    Sweep of sell-side liquidity: bar wicks below an equal-low level but closes
    back above it (bullish). Sweep of buy-side liquidity: bar wicks above an
    equal-high level but closes back below it (bearish). The pool must have
    formed before the sweep bar.
    """
    n = len(df)
    start = max(0, n - max_age_bars)
    best: Optional[LiquiditySweep] = None
    for i in range(n - 1, start - 1, -1):
        high = float(df["high"].iloc[i])
        low = float(df["low"].iloc[i])
        close = float(df["close"].iloc[i])
        bar_time = _bar_time_iso(df, i)
        for pool in sell_side_pools:
            if pool.last_touch_index >= i:
                continue
            if low < pool.level and close > pool.level:
                return LiquiditySweep(
                    side="sell_side", bias="bullish", level=pool.level,
                    bars_ago=n - 1 - i, bar_time=bar_time,
                )
        for pool in buy_side_pools:
            if pool.last_touch_index >= i:
                continue
            if high > pool.level and close < pool.level:
                return LiquiditySweep(
                    side="buy_side", bias="bearish", level=pool.level,
                    bars_ago=n - 1 - i, bar_time=bar_time,
                )
    return best


def classify_structure(
    highs: Sequence[float],
    lows: Sequence[float],
    swing_highs: Sequence[int],
    swing_lows: Sequence[int],
) -> str:
    """HH/HL → bullish, LH/LL → bearish, otherwise range."""
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "unknown"
    h1, h2 = highs[swing_highs[-2]], highs[swing_highs[-1]]
    l1, l2 = lows[swing_lows[-2]], lows[swing_lows[-1]]
    if h2 > h1 and l2 > l1:
        return "bullish"
    if h2 < h1 and l2 < l1:
        return "bearish"
    return "range"


def classify_zone(df, lookback: int = 100) -> str:
    """Premium/discount/equilibrium relative to the recent range."""
    window = df.tail(lookback)
    range_high = float(window["high"].max())
    range_low = float(window["low"].min())
    if range_high <= range_low:
        return "equilibrium"
    position = (float(df["close"].iloc[-1]) - range_low) / (range_high - range_low)
    if position >= PREMIUM_ABOVE:
        return "premium"
    if position <= DISCOUNT_BELOW:
        return "discount"
    return "equilibrium"


def _bar_time_iso(df, i: int) -> str:
    try:
        value = df["time"].iloc[i]
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
    except Exception:
        return ""


def scan_dataframe(df, timeframe: str, sweep_max_age_bars: int = 20) -> TimeframeScan:
    """Run every detector over one timeframe's OHLC DataFrame.

    Expects columns high/low/close (and optionally time). Deterministic.
    """
    import pandas as pd

    highs = df["high"].astype(float).tolist()
    lows = df["low"].astype(float).tolist()
    close = df["close"].astype(float)

    tr = pd.concat(
        [df["high"] - df["low"],
         (df["high"] - close.shift()).abs(),
         (df["low"] - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1] or 0.0)
    tolerance = max(atr * POOL_ATR_TOLERANCE, 1e-12)

    swing_highs, swing_lows = find_swings(highs, lows)
    buy_side = find_pools(highs, swing_highs, tolerance, "buy_side")
    sell_side = find_pools(lows, swing_lows, tolerance, "sell_side")

    return TimeframeScan(
        timeframe=timeframe,
        bars=len(df),
        last_close=float(close.iloc[-1]),
        bar_time=_bar_time_iso(df, len(df) - 1),
        atr=atr,
        structure=classify_structure(highs, lows, swing_highs, swing_lows),
        zone=classify_zone(df),
        buy_side_pools=buy_side,
        sell_side_pools=sell_side,
        recent_sweep=find_recent_sweep(df, buy_side, sell_side, sweep_max_age_bars),
    )


# ─── MT5 fetch + map assembly ───────────────────────────────────────────────


def _fetch_mt5_bars(symbol: str, timeframe: str, count: int):
    """Fetch OHLC bars from the broker. Raises on unavailability."""
    import MetaTrader5 as mt5
    import pandas as pd

    tf = getattr(mt5, f"TIMEFRAME_{timeframe.upper()}", None)
    if tf is None:
        raise RuntimeError(f"unknown timeframe {timeframe}")
    already_initialized = mt5.terminal_info() is not None
    if not already_initialized and not mt5.initialize():
        raise RuntimeError(f"MT5 initialization failed: {mt5.last_error()}")
    try:
        mt5.symbol_select(symbol.upper(), True)
        raw = mt5.copy_rates_from_pos(symbol.upper(), tf, 0, count)
        if raw is None or len(raw) < 60:
            raise RuntimeError(f"insufficient {timeframe} bars for {symbol}")
        df = pd.DataFrame(raw)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df
    finally:
        if not already_initialized:
            mt5.shutdown()


def build_liquidity_map(
    symbol: str,
    timeframes: Optional[Sequence[str]] = None,
    sweep_max_age_bars: int = 20,
) -> LiquidityMap:
    """Scan every timeframe for ``symbol``; per-timeframe errors are recorded,
    never raised, so one missing timeframe can't hide the rest."""
    lmap = LiquidityMap(
        symbol=symbol.upper(),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    for tf in (timeframes or list(TIMEFRAME_BARS)):
        try:
            df = _fetch_mt5_bars(symbol, tf, TIMEFRAME_BARS.get(tf, 200))
            lmap.scans[tf] = scan_dataframe(df, tf, sweep_max_age_bars)
        except Exception as exc:
            logger.warning("Liquidity scan failed for %s %s: %s", symbol, tf, exc)
            lmap.scans[tf] = TimeframeScan(
                timeframe=tf, bars=0, last_close=0.0, bar_time="", atr=0.0,
                structure="unknown", zone="equilibrium", error=str(exc),
            )
    return lmap


# ─── Hard pre-trade gate ────────────────────────────────────────────────────


def qualify_liquidity_setup(
    lmap: LiquidityMap,
    signal: str,
    *,
    sweep_max_age_bars: int = 20,
) -> Tuple[bool, str]:
    """Deterministic go/no-go: is there a real liquidity pattern behind ``signal``?

    BUY requires: a recent sell-side (bullish) sweep on M1/M5/M15, at least one
    readable H1/H4 structure that is not bearish, and price not in the premium
    zone on H1. SELL is the mirror image. Missing data fails closed.
    """
    signal = (signal or "").upper()
    if signal not in ("BUY", "SELL"):
        return False, f"signal {signal or '?'} is not tradeable"

    want_bias = "bullish" if signal == "BUY" else "bearish"

    # 1) A qualifying sweep on a lower timeframe.
    sweeps = []
    lower_available = 0
    for tf in LOWER_TIMEFRAMES:
        scan = lmap.scans.get(tf)
        if scan is None or scan.error:
            continue
        lower_available += 1
        s = scan.recent_sweep
        if s and s.bias == want_bias and s.bars_ago <= sweep_max_age_bars:
            sweeps.append((tf, s))
    if lower_available == 0:
        return False, "liquidity scan unavailable on all lower timeframes (M1/M5/M15) — failing closed"
    if not sweeps:
        side = "sell-side" if signal == "BUY" else "buy-side"
        return False, (
            f"no recent {side} liquidity sweep on M1/M5/M15 "
            f"(within {sweep_max_age_bars} bars) to justify {signal}"
        )

    # 2) Higher-timeframe structure must not oppose the trade.
    higher_scans = [
        lmap.scans[tf] for tf in HIGHER_TIMEFRAMES
        if lmap.scans.get(tf) is not None and not lmap.scans[tf].error
    ]
    if not higher_scans:
        return False, "higher-timeframe (H1/H4) data unavailable — failing closed"
    opposing = "bearish" if signal == "BUY" else "bullish"
    readable = [s for s in higher_scans if s.structure != "unknown"]
    if readable and all(s.structure == opposing for s in readable):
        return False, (
            f"H1/H4 market structure is uniformly {opposing} — refusing {signal} against structure"
        )

    # 3) Don't buy premium / sell discount (H1 range position).
    h1 = lmap.scans.get("H1")
    if h1 is not None and not h1.error:
        if signal == "BUY" and h1.zone == "premium":
            return False, "price is in the H1 premium zone — refusing to buy premium"
        if signal == "SELL" and h1.zone == "discount":
            return False, "price is in the H1 discount zone — refusing to sell discount"

    sweep_tf, sweep = sweeps[0]
    structures = ", ".join(f"{s.timeframe}:{s.structure}" for s in higher_scans)
    return True, (
        f"{signal} qualified by liquidity: {sweep.side} sweep on {sweep_tf} "
        f"@ {sweep.level:g} ({sweep.bars_ago} bars ago); structure [{structures}]; "
        f"H1 zone {h1.zone if h1 and not h1.error else 'n/a'}"
    )
