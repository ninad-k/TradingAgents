"""CLI: backtest the TradingAgents ensemble over a historical window.

Example:
    python backtester.py --ticker XAUUSD --start 2024-01-01 --end 2024-03-01 --cadence 5
"""
from __future__ import annotations

import argparse
import hashlib
import json

from dotenv import load_dotenv

from tradingagents.backtesting.controller import BacktestController
from tradingagents.backtesting.data import (
    TradingViewBarProvider, YFinanceBarProvider, get_spec,
)
from tradingagents.backtesting.decision_cache import DecisionCache
from tradingagents.backtesting.engine import BacktestEngine
from tradingagents.backtesting.output import render_summary
from tradingagents.backtesting.position_models import EquitySharesModel, ForexLotModel
from tradingagents.backtesting.types import BacktestConfig, InstrumentKind
from tradingagents.default_config import DEFAULT_CONFIG


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Backtest the TradingAgents ensemble.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--start", required=True, dest="start")
    p.add_argument("--end", required=True, dest="end")
    p.add_argument("--timeframe", default="1d", choices=["1d"], help="bar timeframe (only daily supported in v1)")
    p.add_argument("--cadence", type=int, default=5, help="rebalance every N bars")
    p.add_argument("--initial-capital", type=float, default=100_000.0, dest="initial_capital")
    p.add_argument("--max-risk-percent", type=float, default=2.0, dest="max_risk_percent")
    return p.parse_args(argv)


def build_config_hash(agent_config: dict) -> str:
    keys = ("llm_provider", "deep_think_llm", "quick_think_llm",
            "max_debate_rounds", "max_risk_discuss_rounds")
    payload = {k: agent_config.get(k) for k in keys}
    blob = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def main(argv=None):
    load_dotenv()
    ns = parse_args(argv)

    spec = get_spec(ns.ticker)
    agent_config = DEFAULT_CONFIG.copy()
    config_hash = build_config_hash(agent_config)

    config = BacktestConfig(
        ticker=ns.ticker, start_date=ns.start, end_date=ns.end,
        timeframe=ns.timeframe, cadence_bars=ns.cadence,
        initial_capital=ns.initial_capital, max_risk_percent=ns.max_risk_percent,
        agent_config=agent_config,
    )

    # Lazy import so unit tests (which never call main) don't construct LLM clients.
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    graph = TradingAgentsGraph(selected_analysts=list(config.selected_analysts),
                               config=agent_config)

    provider = (TradingViewBarProvider() if spec.kind == InstrumentKind.FOREX
                else YFinanceBarProvider())
    position_model = (ForexLotModel(max_risk_percent=ns.max_risk_percent)
                      if spec.kind == InstrumentKind.FOREX
                      else EquitySharesModel())
    cache = DecisionCache(agent_config["data_cache_dir"], config_hash)
    controller = BacktestController(graph=graph, cache=cache)

    engine = BacktestEngine(config=config, spec=spec, provider=provider,
                            controller=controller, position_model=position_model)
    result = engine.run()
    print(render_summary(result))
    return result


if __name__ == "__main__":
    main()
