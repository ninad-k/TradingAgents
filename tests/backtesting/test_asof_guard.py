import tradingagents.agents.utils.core_stock_tools as cst
import tradingagents.agents.utils.technical_indicators_tools as tit
from tradingagents.dataflows.config import set_config, apply_backtest_asof


def test_apply_backtest_asof_clamps_future_date():
    set_config({"backtest_as_of": "2024-03-01"})
    try:
        assert apply_backtest_asof("2024-12-31") == "2024-03-01"
        assert apply_backtest_asof("2024-01-15") == "2024-01-15"   # earlier untouched
    finally:
        set_config({"backtest_as_of": None})


def test_apply_backtest_asof_noop_when_unset():
    set_config({"backtest_as_of": None})
    assert apply_backtest_asof("2024-12-31") == "2024-12-31"


def test_get_stock_data_clamps_end_date(monkeypatch):
    captured = {}

    def fake_route(method, *args, **kwargs):
        captured["args"] = args
        return "ok"

    monkeypatch.setattr(cst, "route_to_vendor", fake_route)
    set_config({"backtest_as_of": "2024-03-01"})
    try:
        cst.get_stock_data.invoke({"symbol": "AAPL",
                                   "start_date": "2024-01-01",
                                   "end_date": "2024-12-31"})
    finally:
        set_config({"backtest_as_of": None})
    assert captured["args"][2] == "2024-03-01"


def test_get_indicators_clamps_curr_date(monkeypatch):
    captured = {}

    def fake_route(method, *args, **kwargs):
        captured["args"] = args
        return "ok"

    monkeypatch.setattr(tit, "route_to_vendor", fake_route)
    set_config({"backtest_as_of": "2024-03-01"})
    try:
        tit.get_indicators.invoke({"symbol": "AAPL", "indicator": "rsi",
                                   "curr_date": "2024-12-31", "look_back_days": 30})
    finally:
        set_config({"backtest_as_of": None})
    assert captured["args"][2] == "2024-03-01"
