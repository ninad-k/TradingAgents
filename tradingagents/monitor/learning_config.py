"""
Loader for the self-improvement loop's two external config files:

- ``goals.json``         — numeric success/failure targets (read-only at runtime)
- ``learned_params.json`` — tunable knobs the reviewer is allowed to edit

Defaults ship in ``tradingagents/monitor/defaults/``. On first read the loader
copies them to ``~/.tradingagents/config/`` (overridable via env), so the live
files survive package upgrades and the user can edit them in place.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

_PACKAGE_DEFAULTS = Path(__file__).parent / "defaults"

DEFAULT_CONFIG_DIR = os.path.join(
    os.path.expanduser("~"), ".tradingagents", "config"
)


def _config_dir() -> Path:
    path = Path(os.environ.get("TRADINGAGENTS_CONFIG_DIR", DEFAULT_CONFIG_DIR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve(name: str) -> Path:
    live = _config_dir() / name
    if not live.exists():
        shutil.copy(_PACKAGE_DEFAULTS / name, live)
    return live


def goals_path() -> Path:
    return _resolve("goals.json")


def learned_params_path() -> Path:
    return _resolve("learned_params.json")


def load_goals() -> dict[str, Any]:
    with open(goals_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def load_learned_params() -> dict[str, Any]:
    with open(learned_params_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def save_learned_params(params: dict[str, Any]) -> None:
    path = learned_params_path()
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
