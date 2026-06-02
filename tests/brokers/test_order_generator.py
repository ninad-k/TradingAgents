"""Position-sizing correctness for OrderGenerator.

Sizing must use each instrument's pip_value_per_lot (account-USD value of a
one-`point` move per 1.0 lot), not a fixed EURUSD-shaped constant. The old
hardcoded 10.0 mis-sized non-EURUSD instruments ~10x (notably XAUUSD).
"""

from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.brokers.models import AccountInfo, OrderAction, SymbolInfo
from tradingagents.brokers.order_generator import OrderGenerator

ACCOUNT = AccountInfo(
    login=0, server="test", account_type="DEMO", currency="USD",
    balance=10_000.0, equity=10_000.0, free_margin=10_000.0, margin_level=1000.0,
)


def _symbol(name, point, pip_value, *, bid=1.0, spread=2.0):
    return SymbolInfo(
        symbol=name, bid=bid, ask=bid + spread * point, spread=spread,
        digits=5, point=point, min_volume=0.01, max_volume=100.0, volume_step=0.01,
        pip_value_per_lot=pip_value,
    )


def _decision(rating=PortfolioRating.BUY, price_target=None):
    return PortfolioDecision(rating=rating, executive_summary="x",
                             investment_thesis="x", price_target=price_target)


# --- _calculate_volume: instrument-specific pip value ----------------------

def test_volume_eurusd_major():
    # $200 risk, 20-pip stop, $10/pip-lot -> 200 / (20 * 10) = 1.0 lot
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("EURUSD", 0.0001, 10.0)
    vol = gen._calculate_volume(OrderAction.BUY, 1.10000, 1.09800, sym, ACCOUNT)
    assert abs(vol - 1.0) < 1e-9


def test_volume_usdjpy():
    # 50-pip stop, $6.7/pip-lot -> 200 / (50 * 6.7) = 0.597 -> 0.60 (step 0.01)
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("USDJPY", 0.01, 6.7, bid=150.0)
    vol = gen._calculate_volume(OrderAction.BUY, 150.000, 149.500, sym, ACCOUNT)
    assert abs(vol - 0.60) < 1e-9


def test_volume_xauusd_is_not_eurusd_shaped():
    # 900-point stop, $1/point-lot -> 200 / (900 * 1) = 0.222 -> 0.22 lot.
    # The old fixed 10.0 would have produced ~0.02 (10x too small).
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("XAUUSD", 0.01, 1.0, bid=2000.0)
    vol = gen._calculate_volume(OrderAction.BUY, 2000.00, 1991.00, sym, ACCOUNT)
    assert abs(vol - 0.22) < 1e-9


# --- _calculate_loss_amount: instrument-specific ---------------------------

def test_loss_amount_xauusd():
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("XAUUSD", 0.01, 1.0, bid=2000.0)
    loss = gen._calculate_loss_amount(2000.00, 1991.00, 0.22, sym)
    assert abs(loss - 198.0) < 1e-9  # 900 points * 0.22 lot * $1


def test_loss_amount_eurusd():
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("EURUSD", 0.0001, 10.0)
    loss = gen._calculate_loss_amount(1.10000, 1.09800, 1.0, sym)
    assert abs(loss - 200.0) < 1e-9  # 20 pips * 1.0 lot * $10


# --- refuse-to-size when pip value is unknown ------------------------------

def test_refuse_to_size_when_pip_value_missing():
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("XAUUSD", 0.01, None, bid=2000.0)
    assert gen._calculate_volume(OrderAction.BUY, 2000.0, 1991.0, sym, ACCOUNT) == 0.0


def test_refuse_to_size_when_pip_value_nonpositive():
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("XAUUSD", 0.01, 0.0, bid=2000.0)
    assert gen._calculate_volume(OrderAction.BUY, 2000.0, 1991.0, sym, ACCOUNT) == 0.0


def test_loss_amount_none_when_pip_value_missing():
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("XAUUSD", 0.01, None, bid=2000.0)
    assert gen._calculate_loss_amount(2000.0, 1991.0, 0.22, sym) is None


def test_decision_to_order_refuses_when_pip_value_missing():
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("XAUUSD", 0.01, None, bid=2000.0, spread=30.0)
    order = gen.decision_to_order(
        _decision(PortfolioRating.BUY, price_target=2050.0),
        "XAUUSD", sym, ACCOUNT, decision_id="t1")
    assert order is None


# --- full public path: XAUUSD risks ~the configured percent ----------------

def test_decision_to_order_xauusd_risk_matches_percent():
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("XAUUSD", 0.01, 1.0, bid=2000.0, spread=30.0)
    order = gen.decision_to_order(
        _decision(PortfolioRating.BUY, price_target=2050.0),
        "XAUUSD", sym, ACCOUNT, decision_id="t2")
    assert order is not None
    assert order.volume > 1.0  # ~1.67 lots; the old bug gave ~0.17
    # Max loss should land near the intended 2% of $10k = $200 (volume rounding aside)
    assert 190.0 <= order.max_loss_per_trade <= 210.0
    assert order.comment == "TradingAgent2.0"


def test_propose_order_risk_per_trade_is_instrument_correct():
    gen = OrderGenerator(max_risk_percent=2.0)
    sym = _symbol("XAUUSD", 0.01, 1.0, bid=2000.0, spread=30.0)
    pending = gen.propose_order(
        _decision(PortfolioRating.BUY, price_target=2050.0),
        "XAUUSD", sym, ACCOUNT, decision_id="t3")
    assert pending is not None
    assert 190.0 <= pending.risk_per_trade <= 210.0
