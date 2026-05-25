"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
from unittest.mock import MagicMock, patch

import pytest


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")


_API_KEY_ENV_VARS = (
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "ZHIPU_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
)


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for env_var in _API_KEY_ENV_VARS:
        monkeypatch.setenv(env_var, os.environ.get(env_var, "placeholder"))


@pytest.fixture()
def mock_llm_client():
    client = MagicMock()
    client.get_llm.return_value = MagicMock()
    with patch(
        "tradingagents.llm_clients.factory.create_llm_client",
        return_value=client,
    ):
        yield client


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    """Isolate the SQLite store, learning config dir, and proposals dir per test.

    Each test gets a fresh DB and clean config/proposals directories so
    schema migrations, seed defaults, and on-disk learned_params writes
    don't bleed between tests.
    """
    monkeypatch.setenv("TRADINGAGENTS_STORE_PATH", str(tmp_path / "store.sqlite3"))
    monkeypatch.setenv("TRADINGAGENTS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TRADINGAGENTS_PROPOSALS_DIR", str(tmp_path / "proposals"))
    from tradingagents.monitor import store
    store._INITIALISED_PATHS.clear()
    yield tmp_path
    store._INITIALISED_PATHS.clear()
