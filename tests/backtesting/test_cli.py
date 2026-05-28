from backtester import build_config_hash, parse_args


def test_parse_args_defaults():
    ns = parse_args(["--ticker", "XAUUSD", "--start", "2024-01-01", "--end", "2024-03-01"])
    assert ns.ticker == "XAUUSD"
    assert ns.cadence == 5
    assert ns.timeframe == "1d"
    assert ns.initial_capital == 100_000.0


def test_config_hash_is_stable_and_sensitive():
    base = {"llm_provider": "ollama", "deep_think_llm": "qwen3.6:latest"}
    assert build_config_hash(base) == build_config_hash(dict(base))
    assert build_config_hash(base) != build_config_hash({**base, "deep_think_llm": "gpt-5.4"})
