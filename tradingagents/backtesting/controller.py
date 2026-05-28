from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, parse_pm_decision
from tradingagents.dataflows.config import set_config

from .decision_cache import DecisionCache


class BacktestController:
    """Bridge: run the agent ensemble for one bar, with as-of guard and caching."""

    def __init__(self, graph, cache: DecisionCache) -> None:
        self._graph = graph
        self._cache = cache

    def decide(self, symbol: str, date: str) -> PortfolioDecision:
        cached = self._cache.get(symbol, date)
        if cached is not None:
            return parse_pm_decision(cached)

        set_config({"backtest_as_of": date})
        try:
            final_state, _ = self._graph.propagate(symbol, date)
            markdown = final_state["final_trade_decision"]
        finally:
            set_config({"backtest_as_of": None})

        self._cache.put(symbol, date, markdown)
        return parse_pm_decision(markdown)
