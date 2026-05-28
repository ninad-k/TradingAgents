from tradingagents.backtesting.decision_cache import DecisionCache


def test_put_get_roundtrip(tmp_path):
    cache = DecisionCache(str(tmp_path), config_hash="abc123")
    assert cache.get("XAUUSD", "2024-03-01") is None
    cache.put("XAUUSD", "2024-03-01", "**Rating**: Buy")
    assert cache.get("XAUUSD", "2024-03-01") == "**Rating**: Buy"


def test_config_hash_isolates_entries(tmp_path):
    a = DecisionCache(str(tmp_path), config_hash="aaa")
    b = DecisionCache(str(tmp_path), config_hash="bbb")
    a.put("AAPL", "2024-03-01", "**Rating**: Buy")
    assert b.get("AAPL", "2024-03-01") is None
