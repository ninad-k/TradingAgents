from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.backtesting.types import Bar, InstrumentKind, InstrumentSpec
from tradingagents.backtesting.position_models import EquitySharesModel, ForexLotModel

EQ = InstrumentSpec("AAPL", InstrumentKind.EQUITY, 0.01, 0.0, 1, 1e9, 1, 0.0)
FX = InstrumentSpec("XAUUSD", InstrumentKind.FOREX, 0.01, 1.0, 0.01, 100, 0.01, 30.0)
BAR = Bar(date="2024-03-01", open=100.0, high=101.0, low=99.0, close=100.0)


def _decision(rating, price_target=None):
    return PortfolioDecision(rating=rating, executive_summary="x",
                             investment_thesis="x", price_target=price_target)


def test_equity_hold_returns_none():
    assert EquitySharesModel().build_order(_decision(PortfolioRating.HOLD), EQ, BAR, 10_000.0) is None


def test_equity_buy_sizes_by_equity_fraction():
    intent = EquitySharesModel(buy_fraction=0.05).build_order(
        _decision(PortfolioRating.BUY, price_target=120.0), EQ, BAR, 10_000.0)
    assert intent.side == "BUY"
    # 5% of 10k = $500 / $100 close = 5 shares
    assert intent.volume == 5
    assert intent.take_profit == 120.0


def test_forex_buy_uses_order_generator_lots_and_levels():
    intent = ForexLotModel(max_risk_percent=2.0).build_order(
        _decision(PortfolioRating.BUY, price_target=2050.0), FX, Bar(
            date="2024-03-01", open=2000.0, high=2010.0, low=1990.0, close=2000.0), 10_000.0)
    assert intent.side == "BUY"
    assert intent.volume > 0
    assert intent.stop_loss is not None and intent.stop_loss < 2000.0   # SL below entry for long
    assert intent.take_profit == 2050.0


def test_forex_hold_returns_none():
    assert ForexLotModel().build_order(_decision(PortfolioRating.HOLD), FX, BAR, 10_000.0) is None
