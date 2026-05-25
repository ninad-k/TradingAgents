"""
Self-improvement reviewer.

Reads the recent decision ledger + outcomes, scores performance against
``goals.json``, and asks the configured LLM for **one** parameter delta
against ``learned_params.json``. The proposal is always written to
``~/.tradingagents/proposals/`` and ``learned_params_history``. It is only
applied to the live ``learned_params.json`` when the env flag
``TRADINGAGENTS_REVIEWER_AUTO_APPLY=1`` is set — review-only by default.

The single-variable rule is enforced after the LLM responds: if the diff
touches more than one key, the proposal is recorded but rejected.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from tradingagents.monitor import learning_config, store

logger = logging.getLogger(__name__)


PROPOSALS_DIR = Path(
    os.environ.get(
        "TRADINGAGENTS_PROPOSALS_DIR",
        os.path.join(os.path.expanduser("~"), ".tradingagents", "proposals"),
    )
)


@dataclass
class Scoreboard:
    n_decisions: int
    n_evaluated: int
    win_rate: Optional[float]
    mean_pnl_pct: Optional[float]
    stdev_pnl_pct: Optional[float]
    sharpe: Optional[float]
    max_drawdown_pct: Optional[float]
    total_return_pct: Optional[float]
    per_signal: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_decisions": self.n_decisions,
            "n_evaluated": self.n_evaluated,
            "win_rate": self.win_rate,
            "mean_pnl_pct": self.mean_pnl_pct,
            "stdev_pnl_pct": self.stdev_pnl_pct,
            "sharpe": self.sharpe,
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_return_pct": self.total_return_pct,
            "per_signal": self.per_signal,
        }


@dataclass
class ReviewResult:
    scoreboard: Scoreboard
    goals: dict[str, Any]
    params_before: dict[str, Any]
    proposal: Optional[dict[str, Any]]  # {"key", "old", "new", "rationale"} or None
    applied: bool
    rejection_reason: Optional[str]
    proposal_path: Optional[Path]


# ─── Scoring ───────────────────────────────────────────────────────────────


def build_scoreboard(window_days: int) -> Scoreboard:
    since = datetime.now() - timedelta(days=window_days)
    rows = store.recent_decisions_with_outcomes(since=since, limit=10000)
    pnls = [r["pnl_pct"] for r in rows if r.get("pnl_pct") is not None]
    n_evaluated = len(pnls)

    if n_evaluated == 0:
        return Scoreboard(
            n_decisions=len(rows),
            n_evaluated=0,
            win_rate=None,
            mean_pnl_pct=None,
            stdev_pnl_pct=None,
            sharpe=None,
            max_drawdown_pct=None,
            total_return_pct=None,
            per_signal={},
        )

    wins = sum(1 for p in pnls if p > 0)
    win_rate = wins / n_evaluated
    mean = sum(pnls) / n_evaluated
    if n_evaluated > 1:
        var = sum((p - mean) ** 2 for p in pnls) / (n_evaluated - 1)
        std = math.sqrt(var)
    else:
        std = 0.0
    sharpe = (mean / std) if std > 0 else None

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cumulative += p
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)

    per_signal: dict[str, dict[str, float]] = {}
    for sig in ("BUY", "SELL", "HOLD"):
        sig_pnls = [
            r["pnl_pct"] for r in rows
            if r.get("pnl_pct") is not None and (r.get("signal") or "").upper() == sig
        ]
        if not sig_pnls:
            continue
        sig_wins = sum(1 for p in sig_pnls if p > 0)
        per_signal[sig] = {
            "count": len(sig_pnls),
            "win_rate": sig_wins / len(sig_pnls),
            "mean_pnl_pct": sum(sig_pnls) / len(sig_pnls),
        }

    return Scoreboard(
        n_decisions=len(rows),
        n_evaluated=n_evaluated,
        win_rate=win_rate,
        mean_pnl_pct=mean,
        stdev_pnl_pct=std,
        sharpe=sharpe,
        max_drawdown_pct=max_dd,
        total_return_pct=cumulative,
        per_signal=per_signal,
    )


# ─── LLM call ──────────────────────────────────────────────────────────────


_PROPOSAL_RE = re.compile(r"\{[^{}]*\"key\"[\s\S]*?\}")


def _ask_llm_for_delta(prompt: str) -> Optional[str]:
    """Ask the configured LLM. Returns raw text, or None if unavailable."""
    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.llm_clients import create_llm_client
    except Exception as e:
        logger.warning("Reviewer cannot import LLM client: %s", e)
        return None
    try:
        client = create_llm_client(
            provider=DEFAULT_CONFIG["llm_provider"],
            model=DEFAULT_CONFIG["quick_think_llm"],
            base_url=DEFAULT_CONFIG.get("backend_url"),
        )
        llm = client.get_llm()
        resp = llm.invoke(prompt)
        # LangChain returns an AIMessage; .content holds the text.
        return getattr(resp, "content", None) or str(resp)
    except Exception as e:
        logger.warning("Reviewer LLM call failed: %s", e)
        return None


def _build_prompt(
    goals: dict[str, Any],
    scoreboard: Scoreboard,
    params: dict[str, Any],
    sample_decisions: list[dict[str, Any]],
) -> str:
    return (
        "You are tuning a trading strategy's parameters. Apply the scientific "
        "method: change EXACTLY ONE parameter, justify it, predict the effect.\n\n"
        "GOALS (numeric targets):\n"
        f"{json.dumps(goals, indent=2)}\n\n"
        "RECENT PERFORMANCE (window scoreboard):\n"
        f"{json.dumps(scoreboard.to_dict(), indent=2)}\n\n"
        "CURRENT learned_params.json (the ONLY thing you may edit):\n"
        f"{json.dumps(params, indent=2)}\n\n"
        f"SAMPLE OF {len(sample_decisions)} RECENT DECISIONS (most recent first):\n"
        f"{json.dumps(sample_decisions, indent=2, default=str)[:4000]}\n\n"
        "Respond with a SINGLE JSON object and nothing else, exactly this shape:\n"
        "{\n"
        '  "key": "<one key from learned_params>",\n'
        '  "old": <current value>,\n'
        '  "new": <proposed value, same type as old>,\n'
        '  "rationale": "<one or two sentences explaining WHY, tied to the data>"\n'
        "}\n"
        "Rules: exactly one key. Same type. Do not invent new keys. "
        "If the data is insufficient to justify a change, return "
        '{"key": null, "rationale": "insufficient evidence"}.'
    )


# ─── Validation ────────────────────────────────────────────────────────────


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    # Try direct parse first, then a regex fallback.
    candidates = [text]
    match = _PROPOSAL_RE.search(text)
    if match:
        candidates.append(match.group(0))
    # Also try the largest {...} blob.
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{") : text.rfind("}") + 1])
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _validate_delta(
    proposal: Optional[dict[str, Any]], current: dict[str, Any]
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    if not proposal:
        return None, "no JSON proposal parsed"
    key = proposal.get("key")
    if key is None:
        return None, proposal.get("rationale") or "reviewer declined to propose"
    if key not in current:
        return None, f"unknown key {key!r} not in learned_params"
    old = proposal.get("old", current[key])
    new = proposal.get("new")
    if new is None:
        return None, "missing 'new' value"
    if type(new) is not type(current[key]):
        return None, (
            f"type mismatch on {key!r}: "
            f"current {type(current[key]).__name__}, new {type(new).__name__}"
        )
    if new == current[key]:
        return None, "proposal is a no-op"
    return {
        "key": key,
        "old": current[key],
        "new": new,
        "rationale": proposal.get("rationale", ""),
    }, None


# ─── Public entry point ───────────────────────────────────────────────────


def run_review(auto_apply: Optional[bool] = None) -> ReviewResult:
    """Build a scoreboard, ask the LLM for one delta, write the proposal.

    ``auto_apply`` defaults to env ``TRADINGAGENTS_REVIEWER_AUTO_APPLY=1``.
    """
    if auto_apply is None:
        auto_apply = os.environ.get(
            "TRADINGAGENTS_REVIEWER_AUTO_APPLY", "0"
        ).lower() in ("1", "true", "yes")

    goals = learning_config.load_goals()
    params_before = learning_config.load_learned_params()
    window_days = int(goals.get("review_window_days", 30))
    scoreboard = build_scoreboard(window_days)

    min_n = int(goals.get("min_decisions_for_review", 20))
    if scoreboard.n_evaluated < min_n:
        proposal_path = _write_proposal_md(
            goals, scoreboard, params_before, proposal=None,
            applied=False, reason=f"insufficient data: {scoreboard.n_evaluated}/{min_n}",
        )
        return ReviewResult(
            scoreboard=scoreboard, goals=goals, params_before=params_before,
            proposal=None, applied=False,
            rejection_reason="insufficient data", proposal_path=proposal_path,
        )

    since = datetime.now() - timedelta(days=window_days)
    sample = store.recent_decisions_with_outcomes(since=since, limit=15)

    raw = _ask_llm_for_delta(_build_prompt(goals, scoreboard, params_before, sample))
    parsed = _extract_json(raw or "")
    proposal, rejection = _validate_delta(parsed, params_before)

    applied = False
    new_params = params_before
    if proposal is not None and auto_apply:
        new_params = dict(params_before)
        new_params[proposal["key"]] = proposal["new"]
        learning_config.save_learned_params(new_params)
        applied = True

    diff = (
        {proposal["key"]: {"from": proposal["old"], "to": proposal["new"]}}
        if proposal else None
    )
    store.record_params_proposal(
        params=new_params,
        diff=diff,
        rationale=(proposal or {}).get("rationale") if proposal else rejection,
        applied=applied,
    )

    proposal_path = _write_proposal_md(
        goals, scoreboard, params_before, proposal, applied, rejection,
    )
    return ReviewResult(
        scoreboard=scoreboard,
        goals=goals,
        params_before=params_before,
        proposal=proposal,
        applied=applied,
        rejection_reason=rejection,
        proposal_path=proposal_path,
    )


def _write_proposal_md(
    goals: dict[str, Any],
    scoreboard: Scoreboard,
    params_before: dict[str, Any],
    proposal: Optional[dict[str, Any]],
    applied: bool,
    reason: Optional[str],
) -> Path:
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    fname = datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".md"
    path = PROPOSALS_DIR / fname
    status = "APPLIED" if applied else ("REJECTED" if reason and not proposal else "PROPOSED (review-only)")
    lines = [
        f"# Reviewer proposal — {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"**Status:** {status}",
        "",
        "## Goals",
        "```json",
        json.dumps(goals, indent=2),
        "```",
        "",
        "## Scoreboard",
        "```json",
        json.dumps(scoreboard.to_dict(), indent=2),
        "```",
        "",
        "## Current learned_params",
        "```json",
        json.dumps(params_before, indent=2),
        "```",
        "",
        "## Proposal",
    ]
    if proposal:
        lines += [
            "```json",
            json.dumps(proposal, indent=2),
            "```",
            "",
            f"**Rationale:** {proposal.get('rationale', '')}",
        ]
    else:
        lines += [f"_None._ Reason: `{reason or 'unknown'}`"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
