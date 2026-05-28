from tradingagents.agents.schemas import (
    PortfolioDecision, PortfolioRating, render_pm_decision, parse_pm_decision,
)


def test_roundtrip_full():
    original = PortfolioDecision(
        rating=PortfolioRating.BUY,
        executive_summary="Enter long, size 5%.",
        investment_thesis="Strong momentum and converging analysts.",
        price_target=2050.0,
        time_horizon="1 week",
        confidence=0.82,
    )
    parsed = parse_pm_decision(render_pm_decision(original))
    assert parsed.rating == PortfolioRating.BUY
    assert parsed.price_target == 2050.0
    assert parsed.time_horizon == "1 week"
    assert round(parsed.confidence, 2) == 0.82


def test_freetext_without_optionals_defaults_to_none():
    parsed = parse_pm_decision("The committee leans Sell here given the breakdown.")
    assert parsed.rating == PortfolioRating.SELL
    assert parsed.price_target is None
    assert parsed.time_horizon is None


def test_missing_rating_defaults_hold():
    parsed = parse_pm_decision("No clear edge in either direction.")
    assert parsed.rating == PortfolioRating.HOLD
