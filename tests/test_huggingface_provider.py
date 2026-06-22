"""Hugging Face provider wiring + the hybrid per-tier provider split.

HF's Inference Providers router is OpenAI-compatible, so the provider rides the
existing OpenAIClient path. These tests pin the router base URL / HF_TOKEN auth,
the accept-any-model behaviour (HF model IDs are open-ended repo names), and the
deep/quick per-tier provider resolution used for a local+HF hybrid.
"""

import warnings

import pytest

import tradingagents.graph.trading_graph as tg
from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.openai_client import OpenAIClient
from tradingagents.llm_clients.model_catalog import get_known_models, get_model_options
from tradingagents.llm_clients.validators import validate_model


# --- provider wiring -------------------------------------------------------

def test_factory_builds_openai_compatible_client_for_huggingface():
    client = create_llm_client("huggingface", "deepseek-ai/DeepSeek-V3-0324")
    assert isinstance(client, OpenAIClient)
    assert client.provider == "huggingface"


def test_huggingface_uses_router_base_url_and_hf_token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test_123")
    llm = create_llm_client("huggingface", "deepseek-ai/DeepSeek-V3-0324").get_llm()
    assert llm.openai_api_base == "https://router.huggingface.co/v1"
    assert llm.openai_api_key.get_secret_value() == "hf_test_123"


def test_huggingface_accepts_any_model_without_warning():
    assert validate_model("huggingface", "some-org/Some-New-Model") is True
    client = create_llm_client("huggingface", "some-org/Some-New-Model")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client.warn_if_unknown_model()
    assert caught == []


def test_catalog_exposes_huggingface_repo_style_ids():
    assert "huggingface" in get_known_models()
    for mode in ("quick", "deep"):
        ids = [value for _, value in get_model_options("huggingface", mode)]
        assert ids, f"no huggingface {mode} models"
        assert any("/" in i for i in ids), "expected HF repo-style ids"


# --- hybrid per-tier provider resolution -----------------------------------

def _resolver():
    # _resolve_llm_config does not touch self; build without running __init__.
    return tg.TradingAgentsGraph.__new__(tg.TradingAgentsGraph)


def _hybrid_cfg(**over):
    cfg = {
        "llm_fallback_enabled": True,
        "llm_prefer_fallback": False,
        "llm_provider": "ollama",
        "quick_think_provider": None,            # -> ollama
        "deep_think_provider": "huggingface",    # remote tier
        "quick_think_llm": "qwen2.5:1.5b",
        "deep_think_llm": "deepseek-ai/DeepSeek-V3-0324",
        "fallback_llm_provider": "ollama",
        "fallback_quick_think_llm": "qwen2.5:1.5b",
        "fallback_deep_think_llm": "qwen2.5:1.5b",
    }
    cfg.update(over)
    return cfg


def test_remote_deep_tier_not_gated_on_local_ollama_models(monkeypatch):
    # Quick (ollama) model is installed; deep is a remote HF id. The HF deep
    # tier must NOT be treated as a missing-ollama-model and must not force a
    # fallback that would collapse the hybrid.
    monkeypatch.setattr(tg, "list_ollama_models", lambda: ["qwen2.5:1.5b"])
    resolved = _resolver()._resolve_llm_config(_hybrid_cfg())
    assert resolved["deep_think_provider"] == "huggingface"
    assert resolved["llm_provider"] == "ollama"


def test_missing_quick_ollama_model_triggers_fallback_and_drops_hybrid(monkeypatch):
    # The local quick model isn't installed -> degrade to the single fallback
    # provider for both tiers (per-tier overrides cleared).
    monkeypatch.setattr(tg, "list_ollama_models", lambda: ["something-else:1b"])
    resolved = _resolver()._resolve_llm_config(_hybrid_cfg())
    assert resolved["llm_provider"] == "ollama"          # fallback_llm_provider
    assert resolved["deep_think_provider"] is None
    assert resolved["quick_think_provider"] is None
    assert resolved["deep_think_llm"] == "qwen2.5:1.5b"


def test_disabled_fallback_preserves_hybrid(monkeypatch):
    monkeypatch.setattr(tg, "list_ollama_models", lambda: [])
    resolved = _resolver()._resolve_llm_config(_hybrid_cfg(llm_fallback_enabled=False))
    assert resolved["deep_think_provider"] == "huggingface"
