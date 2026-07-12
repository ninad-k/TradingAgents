"""Deterministic pre-trade qualification and operational circuit breakers."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional


@dataclass(frozen=True)
class SetupSnapshot:
    symbol: str
    signal: str
    price: float
    ema_fast: float
    ema_slow: float
    ema_trend: float
    rsi: float
    atr: float
    spread: float
    volume_ratio: float
    bar_time: datetime

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["bar_time"] = self.bar_time.isoformat()
        return data


def load_mt5_setup(symbol: str, signal: str, timeframe: str = "M1", bars: int = 120) -> SetupSnapshot:
    """Build a broker-native setup snapshot without relying on an LLM."""
    import MetaTrader5 as mt5
    import pandas as pd

    tf = getattr(mt5, f"TIMEFRAME_{timeframe.upper()}", mt5.TIMEFRAME_M1)
    already_initialized = mt5.terminal_info() is not None
    if not already_initialized and not mt5.initialize():
        raise RuntimeError(f"MT5 initialization failed: {mt5.last_error()}")
    try:
        raw = mt5.copy_rates_from_pos(symbol, tf, 0, max(60, bars))
        tick = mt5.symbol_info_tick(symbol)
        if raw is None or len(raw) < 55 or tick is None:
            raise RuntimeError(f"Insufficient fresh broker bars for {symbol}")
        df = pd.DataFrame(raw)
        close = df["close"].astype(float)
        delta = close.diff()
        avg_gain = delta.clip(lower=0).rolling(14).mean()
        avg_loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = (100 - (100 / (1 + rs))).iloc[-1]
        tr = pd.concat(
            [df.high - df.low, (df.high - close.shift()).abs(), (df.low - close.shift()).abs()],
            axis=1,
        ).max(axis=1)
        volume_avg = float(df.tick_volume.tail(20).mean() or 1.0)
        return SetupSnapshot(
            symbol=symbol.upper(),
            signal=signal.upper(),
            price=float(close.iloc[-1]),
            ema_fast=float(close.ewm(span=9).mean().iloc[-1]),
            ema_slow=float(close.ewm(span=21).mean().iloc[-1]),
            ema_trend=float(close.ewm(span=50).mean().iloc[-1]),
            rsi=float(rsi),
            atr=float(tr.rolling(14).mean().iloc[-1]),
            spread=float(tick.ask - tick.bid),
            volume_ratio=float(df.tick_volume.iloc[-1]) / volume_avg,
            bar_time=datetime.fromtimestamp(int(df.time.iloc[-1]), timezone.utc),
        )
    finally:
        if not already_initialized:
            mt5.shutdown()


def qualify_setup(
    snapshot: SetupSnapshot,
    *,
    max_staleness_seconds: int = 120,
    max_spread_atr_ratio: float = 0.40,
    min_volume_ratio: float = 0.20,
) -> tuple[bool, str]:
    """Require trend, momentum, liquidity, freshness, and sane execution cost."""
    now = datetime.now(timezone.utc)
    # Some MT5 brokers stamp bars in server-local time. Future stamps are tolerated;
    # genuinely old bars are not.
    age = (now - snapshot.bar_time).total_seconds()
    if age > max_staleness_seconds:
        return False, f"stale market data ({age:.0f}s old)"
    if snapshot.atr <= 0:
        return False, "ATR unavailable"
    if snapshot.spread / snapshot.atr > max_spread_atr_ratio:
        return False, f"spread/ATR too high ({snapshot.spread / snapshot.atr:.2f})"
    if snapshot.volume_ratio < min_volume_ratio:
        return False, f"volume confirmation too weak ({snapshot.volume_ratio:.2f}x)"
    if snapshot.signal == "BUY":
        if not (snapshot.ema_fast > snapshot.ema_slow > snapshot.ema_trend and snapshot.rsi >= 52):
            return False, "BUY lacks EMA/RSI alignment"
    elif snapshot.signal == "SELL":
        if not (snapshot.ema_fast < snapshot.ema_slow < snapshot.ema_trend and snapshot.rsi <= 48):
            return False, "SELL lacks EMA/RSI alignment"
    else:
        return False, f"signal {snapshot.signal} is not tradeable"
    return True, "qualified deterministic setup"


def operational_guard(
    *,
    symbol: str,
    positions: Iterable[Any],
    history: Iterable[Any],
    max_total_volume: float,
    cooldown_minutes: int,
    max_consecutive_losses: int,
    max_daily_loss_usd: float,
) -> tuple[bool, str]:
    """Apply portfolio and recent-execution circuit breakers."""
    positions = list(positions)
    if any(str(p.symbol).upper() == symbol.upper() for p in positions):
        return False, f"an open {symbol.upper()} position already exists"
    total_volume = sum(float(getattr(p, "volume", 0.0) or 0.0) for p in positions)
    if total_volume >= max_total_volume:
        return False, f"portfolio volume cap reached ({total_volume:g})"

    rows = sorted(list(history), key=lambda x: getattr(x, "entry_time", datetime.min), reverse=True)
    if rows:
        last_time = getattr(rows[0], "entry_time", None)
        if last_time:
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_time).total_seconds() / 60
            if elapsed < cooldown_minutes:
                return False, f"trade cooldown active ({elapsed:.1f}/{cooldown_minutes}m)"

    consecutive = 0
    for row in rows:
        pnl = getattr(row, "profit", None)
        if pnl is None or pnl >= 0:
            break
        consecutive += 1
    if consecutive >= max_consecutive_losses:
        return False, f"consecutive-loss circuit breaker ({consecutive})"

    today = datetime.now(timezone.utc).date()
    daily_pnl = 0.0
    for row in rows:
        when = getattr(row, "exit_time", None) or getattr(row, "entry_time", None)
        if when and when.date() == today and getattr(row, "profit", None) is not None:
            daily_pnl += float(row.profit)
    if daily_pnl <= -abs(max_daily_loss_usd):
        return False, f"daily loss circuit breaker (${daily_pnl:.2f})"
    return True, "operational checks passed"


def reward_to_cost_ok(order: Any, symbol_info: Any, min_multiple: float = 4.0) -> tuple[bool, str]:
    """Reject orders whose target does not comfortably exceed spread cost."""
    entry = order.entry_price or (symbol_info.ask if order.action.value == "BUY" else symbol_info.bid)
    if order.take_profit is None or not symbol_info.pip_value_per_lot:
        return False, "take-profit or point value unavailable for cost gate"
    reward_points = abs(float(order.take_profit) - float(entry)) / symbol_info.point
    reward_usd = reward_points * symbol_info.pip_value_per_lot * order.volume
    spread_usd = symbol_info.spread * symbol_info.pip_value_per_lot * order.volume
    required = spread_usd * min_multiple
    if reward_usd < required:
        return False, f"expected reward ${reward_usd:.2f} < {min_multiple:g}x spread cost ${spread_usd:.2f}"
    return True, f"reward/cost gate passed ({reward_usd / max(spread_usd, 1e-9):.1f}x)"
