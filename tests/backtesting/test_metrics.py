from tradingagents.backtesting.types import PortfolioValuePoint
from tradingagents.backtesting.metrics import PerformanceMetricsCalculator


def _points(values):
    dates = [f"2024-01-{i+1:02d}" for i in range(len(values))]
    return [PortfolioValuePoint(date=d, value=v) for d, v in zip(dates, values)]


def test_empty_returns_none_metrics():
    m = PerformanceMetricsCalculator().compute_metrics([])
    assert m.sharpe_ratio is None and m.max_drawdown is None


def test_monotonic_increase_has_no_drawdown():
    m = PerformanceMetricsCalculator().compute_metrics(_points([100, 101, 102, 103, 104]))
    assert m.max_drawdown == 0.0
    assert m.max_drawdown_date is None
    assert m.sharpe_ratio is not None


def test_drawdown_is_negative_percentage():
    m = PerformanceMetricsCalculator().compute_metrics(_points([100, 110, 104, 99, 105]))
    assert round(m.max_drawdown, 4) == -10.0
    assert m.max_drawdown_date is not None


def test_total_return_and_ending_value():
    m = PerformanceMetricsCalculator().compute_metrics(_points([100, 110, 120]))
    assert m.ending_value == 120
    assert round(m.total_return_pct, 4) == 20.0
