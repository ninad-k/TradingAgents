"""Mutable application settings used by the dashboard and scheduler."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG

DEFAULT_CONFIG_DIR = os.path.join(
    os.path.expanduser("~"), ".tradingagents", "config"
)

SETTINGS_NAME = "settings.json"

_MUTABLE_KEYS = {
    "llm_provider",
    "deep_think_llm",
    "quick_think_llm",
    "llm_fallback_enabled",
    "llm_prefer_fallback",
    "fallback_llm_provider",
    "fallback_deep_think_llm",
    "fallback_quick_think_llm",
    "watchlist_enabled",
    "watchlist_check_interval_seconds",
    "analysis_timeout_seconds",
    "auto_trade_enabled",
    "auto_trade_paper_only",
    "mock_mode_enabled",
    "trade_comment",
    "max_risk_per_trade_percent",
    "max_risk_per_trade_usd",
    "market_timeframe",
    "llm_enabled",
    "token_budget_max",
}


def _config_dir() -> Path:
    path = Path(os.environ.get("TRADINGAGENTS_CONFIG_DIR", DEFAULT_CONFIG_DIR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return _config_dir() / SETTINGS_NAME


def default_settings() -> dict[str, Any]:
    return {key: DEFAULT_CONFIG[key] for key in _MUTABLE_KEYS if key in DEFAULT_CONFIG}


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        save_settings(default_settings())
    with open(path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    defaults = default_settings()
    merged = {**defaults, **{k: v for k, v in settings.items() if k in _MUTABLE_KEYS}}
    if merged != settings:
        save_settings(merged)
    return merged


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    cleaned = {k: v for k, v in settings.items() if k in _MUTABLE_KEYS}
    existing = default_settings()
    existing.update(cleaned)
    path = settings_path()
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
    return existing


def update_settings(patch: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    for key, value in patch.items():
        if key not in _MUTABLE_KEYS:
            continue
        settings[key] = value
    return save_settings(settings)


def reset_settings() -> dict[str, Any]:
    path = settings_path()
    if path.exists():
        backup = path.with_suffix(".json.bak")
        shutil.copy(path, backup)
    return save_settings(default_settings())
