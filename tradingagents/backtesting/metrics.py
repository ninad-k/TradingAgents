from __future__ import annotations

from typing import Sequence

from .types import PerformanceMetrics, PortfolioValuePoint


class PerformanceMetricsCalculator:
    """Sharpe, Sortino, and max drawdown. Adapted from virattt/ai-hedge-fund (MIT)."""

    def __init__(self, *, annual_trading_days: int = 252, annual_rf_rate: float = 0.0434) -> None:
        self.annual_trading_days = annual_trading_days
        self.annual_rf_rate = annual_rf_rate

    def compute_metrics(self, values: Sequence[PortfolioValuePoint]) -> PerformanceMetrics:
        import numpy as np
        import pandas as pd

        if not values:
            return PerformanceMetrics()

        df = pd.DataFrame({"Date": [v.date for v in values],
                           "Portfolio Value": [v.value for v in values]})
        df = df.set_index("Date")
        ending_value = float(df["Portfolio Value"].iloc[-1])
        starting_value = float(df["Portfolio Value"].iloc[0])
        total_return_pct = ((ending_value - starting_value) / starting_value * 100.0
                            if starting_value else None)

        df["Daily Return"] = df["Portfolio Value"].pct_change()
        clean = df["Daily Return"].dropna()

        sharpe = sortino = None
        if len(clean) >= 2:
            daily_rf = self.annual_rf_rate / self.annual_trading_days
            excess = clean - daily_rf
            mean_excess = excess.mean()
            std_excess = excess.std()
            sharpe = (float(np.sqrt(self.annual_trading_days) * (mean_excess / std_excess))
                      if std_excess > 1e-12 else 0.0)
            downside = float(np.sqrt(np.mean(np.minimum(excess, 0) ** 2)))
            if downside > 1e-12:
                sortino = float(np.sqrt(self.annual_trading_days) * (mean_excess / downside))
            else:
                sortino = float("inf") if mean_excess > 0 else 0.0

        rolling_max = df["Portfolio Value"].cummax()
        drawdown = (df["Portfolio Value"] - rolling_max) / rolling_max
        min_dd = float(drawdown.min()) if len(drawdown) else 0.0
        max_drawdown = float(min_dd * 100.0)
        max_drawdown_date = drawdown.idxmin() if min_dd < 0 else None

        return PerformanceMetrics(
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_drawdown,
            max_drawdown_date=max_drawdown_date,
            total_return_pct=total_return_pct,
            ending_value=ending_value,
        )
