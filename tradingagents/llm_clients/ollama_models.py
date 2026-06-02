"""Helpers for detecting local Ollama models."""

from __future__ import annotations

import json
import urllib.request
from typing import Iterable


def list_ollama_models(base_url: str = "http://localhost:11434") -> list[str]:
    """Return installed Ollama model names, or [] if Ollama is unreachable."""
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    return [
        item.get("name") or item.get("model")
        for item in payload.get("models", [])
        if item.get("name") or item.get("model")
    ]


def has_ollama_model(model: str, installed: Iterable[str] | None = None) -> bool:
    installed_models = set(installed if installed is not None else list_ollama_models())
    return model in installed_models
