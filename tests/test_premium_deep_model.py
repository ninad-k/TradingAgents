"""Premium deep-model switch: kimi-k3:cloud routing via premium_deep_enabled."""

import tradingagents.graph.trading_graph as tg
from tradingagents.monitor import app_settings


def _resolver():
    # _resolve_llm_config does not touch self; build without running __init__.
    return tg.TradingAgentsGraph.__new__(tg.TradingAgentsGraph)


def _cfg(**over):
    cfg = {
        "llm_fallback_enabled": False,
        "llm_prefer_fallback": False,
        "llm_provider": "ollama",
        "quick_think_provider": None,
        "deep_think_provider": None,
        "quick_think_llm": "qwen3:4b",
        "deep_think_llm": "glm-5.2:cloud",
        "premium_deep_enabled": False,
        "premium_deep_llm": "kimi-k3:cloud",
    }
    cfg.update(over)
    return cfg


def test_switch_off_keeps_configured_deep_model(monkeypatch):
    monkeypatch.setattr(tg, "list_ollama_models", lambda: ["qwen3:4b", "glm-5.2:cloud", "kimi-k3:cloud"])
    resolved = _resolver()._resolve_llm_config(_cfg())
    assert resolved["deep_think_llm"] == "glm-5.2:cloud"


def test_switch_on_routes_deep_tier_to_premium_model(monkeypatch):
    monkeypatch.setattr(tg, "list_ollama_models", lambda: ["qwen3:4b", "glm-5.2:cloud", "kimi-k3:cloud"])
    resolved = _resolver()._resolve_llm_config(_cfg(premium_deep_enabled=True))
    assert resolved["deep_think_llm"] == "kimi-k3:cloud"
    assert resolved["deep_think_provider"] == "ollama"
    # Quick tier untouched.
    assert resolved["quick_think_llm"] == "qwen3:4b"


def test_switch_on_but_model_not_pulled_keeps_configured_model(monkeypatch):
    # An un-provisioned toggle must not change the deep tier (and must not
    # trigger the missing-ollama-model fallback collapse either).
    monkeypatch.setattr(tg, "list_ollama_models", lambda: ["qwen3:4b", "glm-5.2:cloud"])
    resolved = _resolver()._resolve_llm_config(
        _cfg(premium_deep_enabled=True, llm_fallback_enabled=True,
             fallback_llm_provider="anthropic",
             fallback_deep_think_llm="claude-sonnet-5",
             fallback_quick_think_llm="claude-sonnet-5")
    )
    assert resolved["deep_think_llm"] == "glm-5.2:cloud"


def test_premium_override_applies_before_fallback_gating(monkeypatch):
    # With the premium model pulled, enabling the switch must survive the
    # ollama installed-model gate (kimi-k3:cloud is in the list).
    monkeypatch.setattr(tg, "list_ollama_models", lambda: ["qwen3:4b", "glm-5.2:cloud", "kimi-k3:cloud"])
    resolved = _resolver()._resolve_llm_config(
        _cfg(premium_deep_enabled=True, llm_fallback_enabled=True,
             fallback_llm_provider="anthropic",
             fallback_deep_think_llm="claude-sonnet-5",
             fallback_quick_think_llm="claude-sonnet-5")
    )
    assert resolved["deep_think_llm"] == "kimi-k3:cloud"
    assert resolved["llm_provider"] == "ollama"


def test_premium_keys_are_dashboard_mutable():
    assert "premium_deep_enabled" in app_settings._MUTABLE_KEYS
    assert "premium_deep_llm" in app_settings._MUTABLE_KEYS
