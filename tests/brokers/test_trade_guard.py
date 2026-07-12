from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from tradingagents.brokers.trade_guard import (
    SetupSnapshot,
    operational_guard,
    qualify_setup,
    reward_to_cost_ok,
)


def _setup(signal="BUY", **overrides):
    data = dict(
        symbol="BTCUSD", signal=signal, price=100.0, ema_fast=103.0,
        ema_slow=102.0, ema_trend=101.0, rsi=58.0, atr=10.0,
        spread=1.0, volume_ratio=1.0, bar_time=datetime.now(timezone.utc),
    )
    data.update(overrides)
    return SetupSnapshot(**data)


def test_setup_requires_alignment_liquidity_and_cost():
    assert qualify_setup(_setup())[0]
    assert not qualify_setup(_setup(volume_ratio=0.05))[0]
    assert not qualify_setup(_setup(spread=5.0))[0]
    assert not qualify_setup(_setup(ema_fast=99.0))[0]


def test_setup_rejects_stale_data():
    stale = _setup(bar_time=datetime.now(timezone.utc) - timedelta(minutes=10))
    assert qualify_setup(stale)[1].startswith("stale market data")


def test_operational_guard_blocks_duplicate_symbol():
    position = SimpleNamespace(symbol="BTCUSD", volume=0.1)
    ok, reason = operational_guard(
        symbol="BTCUSD", positions=[position], history=[], max_total_volume=2,
        cooldown_minutes=15, max_consecutive_losses=3, max_daily_loss_usd=500,
    )
    assert not ok and "already exists" in reason


def test_reward_cost_gate():
    order = SimpleNamespace(
        entry_price=100.0, take_profit=110.0, volume=1.0,
        action=SimpleNamespace(value="BUY"),
    )
    symbol = SimpleNamespace(ask=100.0, bid=99.0, point=1.0, spread=1.0, pip_value_per_lot=1.0)
    assert reward_to_cost_ok(order, symbol, 4.0)[0]
    order.take_profit = 102.0
    assert not reward_to_cost_ok(order, symbol, 4.0)[0]
