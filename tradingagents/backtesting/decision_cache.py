from __future__ import annotations

import os


class DecisionCache:
    """Persist Portfolio Manager markdown per (symbol, date), keyed by config hash."""

    def __init__(self, cache_dir: str, config_hash: str) -> None:
        self._dir = os.path.join(cache_dir, "backtest_decisions", config_hash)
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, symbol: str, date: str) -> str:
        safe = symbol.replace("/", "_").replace(":", "_")
        return os.path.join(self._dir, f"{safe}_{date}.md")

    def get(self, symbol: str, date: str):
        path = self._path(symbol, date)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def put(self, symbol: str, date: str, markdown: str) -> None:
        with open(self._path(symbol, date), "w", encoding="utf-8") as f:
            f.write(markdown)
