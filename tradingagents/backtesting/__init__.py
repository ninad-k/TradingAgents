"""Backtesting for the TradingAgents ensemble.

Structure and the metrics calculator are adapted from virattt/ai-hedge-fund
(`src/backtesting/`), MIT-licensed. See NOTICE in this package.
"""
from .types import BacktestConfig, BacktestResult          # noqa: E402
from .engine import BacktestEngine                          # noqa: E402
from .controller import BacktestController                  # noqa: E402
from .data import get_spec                                  # noqa: E402

__all__ = ["BacktestConfig", "BacktestResult", "BacktestEngine",
           "BacktestController", "get_spec"]
