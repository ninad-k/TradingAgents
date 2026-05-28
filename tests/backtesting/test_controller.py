from tradingagents.agents.schemas import PortfolioRating
from tradingagents.backtesting.controller import BacktestController
from tradingagents.backtesting.decision_cache import DecisionCache
from tradingagents.dataflows.config import get_config


class FakeGraph:
    def __init__(self):
        self.calls = []

    def propagate(self, symbol, date):
        # record the as-of value visible to the agents at decision time
        self.calls.append((symbol, date, get_config().get("backtest_as_of")))
        final_state = {"final_trade_decision": "**Rating**: Buy\n\n**Price Target**: 2050"}
        return final_state, "Buy"


def test_decide_parses_and_caches(tmp_path):
    graph = FakeGraph()
    cache = DecisionCache(str(tmp_path), "h1")
    ctrl = BacktestController(graph=graph, cache=cache)

    d1 = ctrl.decide("XAUUSD", "2024-03-01")
    assert d1.rating == PortfolioRating.BUY
    assert d1.price_target == 2050.0
    assert graph.calls[0][2] == "2024-03-01"        # as-of set during propagate
    assert get_config().get("backtest_as_of") is None   # reset afterwards

    # second call hits cache -> no new propagate
    ctrl.decide("XAUUSD", "2024-03-01")
    assert len(graph.calls) == 1
