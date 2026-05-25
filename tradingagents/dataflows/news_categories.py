"""
Categorized market news aggregation on top of Alpha Vantage NEWS_SENTIMENT.

Pattern ported from HKUDS/AI-Trader's market_intel.py: instead of one ad-hoc
ticker query, expose a small set of named categories (equities, macro, crypto,
commodities, forex) and let callers pull a unified snapshot for the dashboard
or any agent that wants a market overview.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from .alpha_vantage_common import (
    AlphaVantageRateLimitError,
    _make_api_request,
    format_datetime_for_api,
)
from ._backoff import CooldownActive


# Each category maps to NEWS_SENTIMENT params. Either `topics` or `tickers`
# (or both) is supplied — Alpha Vantage accepts either filter.
CATEGORY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "equities": {
        "label": "Equities",
        "description": "Stocks, ETFs, and company market developments.",
        "params": {"topics": "financial_markets"},
    },
    "macro": {
        "label": "Macro",
        "description": "Macro regime, policy, and broad economic context.",
        "params": {"topics": "economy_macro,economy_monetary,economy_fiscal"},
    },
    "crypto": {
        "label": "Crypto",
        "description": "Crypto market headlines anchored on BTC and ETH.",
        "params": {"tickers": "CRYPTO:BTC,CRYPTO:ETH"},
    },
    "commodities": {
        "label": "Commodities",
        "description": "Energy, gold, and commodity-linked events.",
        "params": {"topics": "energy_transportation"},
    },
    "forex": {
        "label": "Forex",
        "description": "Currency markets and FX headlines.",
        "params": {"topics": "finance"},
    },
}


def list_categories() -> list[dict[str, str]]:
    """Return [{key, label, description}] for the dashboard category picker."""
    return [
        {"key": key, "label": meta["label"], "description": meta["description"]}
        for key, meta in CATEGORY_DEFINITIONS.items()
    ]


def _parse_response(raw: dict | str) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _sentiment_summary(feed: list[dict[str, Any]]) -> dict[str, float | int]:
    """Aggregate overall_sentiment_score across articles."""
    if not feed:
        return {"count": 0, "avg_score": 0.0, "bullish": 0, "bearish": 0, "neutral": 0}
    scores: list[float] = []
    bullish = bearish = neutral = 0
    for article in feed:
        try:
            score = float(article.get("overall_sentiment_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        scores.append(score)
        label = (article.get("overall_sentiment_label") or "").lower()
        if "bullish" in label:
            bullish += 1
        elif "bearish" in label:
            bearish += 1
        else:
            neutral += 1
    avg = sum(scores) / len(scores) if scores else 0.0
    return {
        "count": len(feed),
        "avg_score": round(avg, 4),
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
    }


def get_category_news(
    category: str,
    curr_date: str,
    look_back_days: int = 2,
    limit: int = 25,
) -> dict[str, Any]:
    """Fetch news for one category. Returns {category, status, feed?, summary?, error?}."""
    meta = CATEGORY_DEFINITIONS.get(category)
    if not meta:
        return {"category": category, "status": "unknown_category"}

    try:
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    except ValueError:
        return {"category": category, "status": "bad_date", "error": curr_date}

    start_dt = curr_dt - timedelta(days=look_back_days)
    params = dict(meta["params"])
    params.update({
        "time_from": format_datetime_for_api(start_dt.strftime("%Y-%m-%d")),
        "time_to": format_datetime_for_api(curr_date),
        "limit": str(limit),
    })

    try:
        raw = _make_api_request("NEWS_SENTIMENT", params)
    except CooldownActive as exc:
        return {
            "category": category,
            "status": "cooldown",
            "retry_in": round(exc.retry_in, 1),
        }
    except AlphaVantageRateLimitError as exc:
        return {"category": category, "status": "rate_limited", "error": str(exc)}
    except Exception as exc:  # network / transport
        return {"category": category, "status": "error", "error": str(exc)}

    parsed = _parse_response(raw)
    feed = parsed.get("feed") or []
    return {
        "category": category,
        "label": meta["label"],
        "status": "ok",
        "summary": _sentiment_summary(feed),
        "feed": feed[:limit],
    }


def get_market_intel_snapshot(
    curr_date: Optional[str] = None,
    look_back_days: int = 2,
    limit: int = 15,
    categories: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Aggregate snapshot across all (or selected) categories.

    Returns {date, generated_at, categories: [...]} suitable for a dashboard widget.
    """
    if curr_date is None:
        curr_date = datetime.utcnow().strftime("%Y-%m-%d")
    selected = categories or list(CATEGORY_DEFINITIONS.keys())
    return {
        "date": curr_date,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "categories": [
            get_category_news(cat, curr_date, look_back_days, limit)
            for cat in selected
        ],
    }
