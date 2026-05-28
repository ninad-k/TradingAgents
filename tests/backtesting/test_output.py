from tradingagents.backtesting.types import (
    BacktestConfig, BacktestResult, PerformanceMetrics, PortfolioValuePoint, Trade,
)
from tradingagents.backtesting.output import render_summary


def test_render_summary_contains_key_numbers():
    config = BacktestConfig(ticker="XAUUSD", start_date="2024-01-01", end_date="2024-02-01")
    metrics = PerformanceMetrics(sharpe_ratio=1.23, sortino_ratio=2.0,
                                 max_drawdown=-5.5, total_return_pct=12.0,
                                 ending_value=112_000.0)
    result = BacktestResult(config=config,
                            values=[PortfolioValuePoint("2024-01-01", 100_000.0)],
                            trades=[Trade("XAUUSD", "BUY", "2024-01-02", 2000.0, 1.0,
                                          exit_date="2024-01-09", exit_price=2050.0, pnl=5000.0,
                                          exit_reason="TP")],
                            metrics=metrics, benchmark_values=[])
    text = render_summary(result)
    assert "XAUUSD" in text
    assert "Sharpe" in text and "1.23" in text
    assert "Trades: 1" in text
