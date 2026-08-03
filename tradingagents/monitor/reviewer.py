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
    # Information Coefficient of signed conviction vs realized return (Qlib-style):
    # ic = Pearson, rank_ic = Spearman, over actionable (BUY/SELL) evaluated rows.
    ic: Optional[float] = None
    rank_ic: Optional[float] = None
    ic_n: int = 0
    per_confidence_bucket: dict[str, dict[str, float]] = field(default_factory=dict)

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
            "ic": self.ic,
            "rank_ic": self.rank_ic,
            "ic_n": self.ic_n,
            "per_confidence_bucket": self.per_confidence_bucket,
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


_SIGNAL_DIR = {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0}


def _direction(row: dict[str, Any]) -> Optional[float]:
    return _SIGNAL_DIR.get((row.get("signal") or "").upper())


def _conviction_score(row: dict[str, Any]) -> Optional[float]:
    """Signed conviction for one decision: +/- confidence by direction.

    Falls back to the discrete +/-1 sign when no confidence was recorded.
    Returns None for non-actionable / unknown signals.
    """
    direction = _direction(row)
    if direction is None:
        return None
    conf = row.get("confidence")
    if conf is None:
        return direction
    try:
        return direction * float(conf)
    except (TypeError, ValueError):
        return direction


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def _rank(values: list[float]) -> list[float]:
    """Average ranks (1-based), ties share the mean of their positions."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # mean of 1-based positions i+1..j+1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def compute_ic(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """IC / Rank-IC of signed conviction vs raw forward return.

    Only actionable (BUY/SELL) rows with a known ``pnl_pct`` are used: a HOLD
    carries no directional prediction. ``pnl_pct`` is stored already signed by
    direction (positive = correct call), so the raw forward return is recovered
    as ``pnl_pct * direction`` before correlating against the signed conviction
    score. ``ic`` is Pearson, ``rank_ic`` Spearman.
    """
    scores: list[float] = []
    returns: list[float] = []
    for r in rows:
        if r.get("pnl_pct") is None:
            continue
        score = _conviction_score(r)
        direction = _direction(r)
        if score is None or not direction:   # skip HOLD / non-actionable
            continue
        scores.append(score)
        returns.append(float(r["pnl_pct"]) * direction)  # un-sign back to raw return
    n = len(scores)
    if n < 2:
        return {"ic": None, "rank_ic": None, "n": n}
    ic = _pearson(scores, returns)
    rank_ic = _pearson(_rank(scores), _rank(returns))
    return {"ic": ic, "rank_ic": rank_ic, "n": n}


def _confidence_bucket(conf: Optional[float]) -> str:
    if conf is None:
        return "unknown"
    if conf >= 0.7:
        return "high"
    if conf >= 0.5:
        return "medium"
    return "low"


def _build_confidence_buckets(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    buckets: dict[str, list[float]] = {}
    for r in rows:
        if r.get("pnl_pct") is None:
            continue
        buckets.setdefault(_confidence_bucket(r.get("confidence")), []).append(float(r["pnl_pct"]))
    out: dict[str, dict[str, float]] = {}
    for name, pnls in buckets.items():
        wins = sum(1 for p in pnls if p > 0)
        out[name] = {
            "count": len(pnls),
            "win_rate": wins / len(pnls),
            "mean_pnl_pct": sum(pnls) / len(pnls),
        }
    return out


def build_scoreboard(window_days: int, rows: Optional[list[dict[str, Any]]] = None) -> Scoreboard:
    """Score a window. Pass ``rows`` to score an explicit slice (walk-forward);
    otherwise the trailing ``window_days`` are queried from the store."""
    if rows is None:
        since = datetime.now() - timedelta(days=window_days)
        rows = store.recent_decisions_with_outcomes(since=since, limit=10000)
    # Headline stats score ACTIONABLE decisions only. HOLD outcomes are
    # hard-coded to pnl_pct=0.0, so including them floods win_rate/mean with
    # zeros (observed live: 56/67 rows were HOLD, dragging win_rate to 4%
    # when actual SELLs won 60%) and misleads the reviewer LLM. The
    # per-signal breakdown below still reports HOLD separately.
    pnls = [
        r["pnl_pct"] for r in rows
        if r.get("pnl_pct") is not None
        and (r.get("signal") or "").upper() in ("BUY", "SELL")
    ]
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

    ic_stats = compute_ic(rows)
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
        ic=ic_stats["ic"],
        rank_ic=ic_stats["rank_ic"],
        ic_n=ic_stats["n"],
        per_confidence_bucket=_build_confidence_buckets(rows),
    )


# ─── Walk-forward split & validation (RD-Agent hypothesis→test→keep) ─────────


def _split_rows(
    rows: list[dict[str, Any]], holdout_frac: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Chronological train/holdout split: oldest -> train, most-recent -> holdout.

    No leakage: the split is purely by ``decided_at`` ordering, so holdout rows
    are strictly newer than train rows.
    """
    rows_sorted = sorted(rows, key=lambda r: r.get("decided_at") or "")
    n = len(rows_sorted)
    if n == 0:
        return [], []
    holdout_n = max(1, int(round(n * holdout_frac)))
    if n > 1:
        holdout_n = min(holdout_n, n - 1)  # always leave at least one train row
    return rows_sorted[: n - holdout_n], rows_sorted[n - holdout_n:]


def split_window(
    window_days: int, holdout_frac: float = 0.3
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Query the trailing window and split it chronologically into (train, holdout)."""
    since = datetime.now() - timedelta(days=window_days)
    rows = store.recent_decisions_with_outcomes(since=since, limit=10000)
    return _split_rows(rows, holdout_frac)


def _recently_rejected_keys(limit: int = 20) -> dict[str, str]:
    """Map of param key -> why it was last rejected, from proposal history.

    Lets the reviewer avoid re-proposing changes that were already tried and
    rejected (RD-Agent "evolving knowledge", minimal form).
    """
    out: dict[str, str] = {}
    for p in store.list_proposals(status="rejected", limit=limit):
        diff = p.get("diff") or {}
        reason = p.get("rejection_reason") or p.get("rationale") or "previously rejected"
        for key in diff.keys():
            out.setdefault(key, reason)
    return out


def _validation_verdict(
    train_sb: Scoreboard, holdout_sb: Scoreboard, goals: dict[str, Any]
) -> tuple[bool, str]:
    """Out-of-sample guard: apply a change only when the weakness is confirmed
    on the held-out slice (persistent), not a train-window fluke.

    Primary metric is win_rate vs ``min_win_rate``. We can't re-run agents on
    history, so this validates that the *problem* the proposal targets is real
    out-of-sample, rather than chasing noise in the recent window.
    """
    min_wr = goals.get("min_win_rate")
    if min_wr is None:
        return True, "no min_win_rate goal; applying on train evidence alone"
    tw, hw = train_sb.win_rate, holdout_sb.win_rate
    if tw is None or hw is None:
        return False, "cannot validate: train/holdout has no evaluated decisions"
    if tw < min_wr and hw < min_wr:
        return True, (
            f"weakness persists out-of-sample (train win_rate {tw:.2f}, "
            f"holdout {hw:.2f} < goal {min_wr:.2f})"
        )
    return False, (
        f"weakness not confirmed out-of-sample (train win_rate {tw:.2f}, "
        f"holdout {hw:.2f}); likely noise — not applied"
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
    train_sb: Scoreboard,
    holdout_sb: Scoreboard,
    params: dict[str, Any],
    sample_decisions: list[dict[str, Any]],
    rejected_keys: dict[str, str],
) -> str:
    rejected_block = (
        "ALREADY TRIED AND REJECTED (do NOT propose these keys again):\n"
        f"{json.dumps(rejected_keys, indent=2)}\n\n"
        if rejected_keys else ""
    )
    return (
        "You are tuning a trading strategy's parameters using the scientific "
        "method (walk-forward). Form ONE hypothesis: identify the weakest metric "
        "on the TRAIN scoreboard, explain WHY it is weak, and change EXACTLY ONE "
        "parameter you predict will improve it. Your change will be validated "
        "against the HOLDOUT scoreboard before it is applied.\n\n"
        "Metrics note: `ic`/`rank_ic` are the Information Coefficient of decision "
        "conviction vs realized forward return (range -1..1; higher = better "
        "calibrated). `per_confidence_bucket` shows win-rate by conviction tier.\n\n"
        "GOALS (numeric targets):\n"
        f"{json.dumps(goals, indent=2)}\n\n"
        "TRAIN scoreboard (older slice — form the hypothesis here):\n"
        f"{json.dumps(train_sb.to_dict(), indent=2)}\n\n"
        "HOLDOUT scoreboard (most-recent slice — your change is validated here):\n"
        f"{json.dumps(holdout_sb.to_dict(), indent=2)}\n\n"
        f"{rejected_block}"
        "CURRENT learned_params.json (the ONLY thing you may edit):\n"
        f"{json.dumps(params, indent=2)}\n\n"
        f"SAMPLE OF {len(sample_decisions)} RECENT DECISIONS (most recent first):\n"
        f"{json.dumps(sample_decisions, indent=2, default=str)[:4000]}\n\n"
        "Respond with a SINGLE JSON object and nothing else, exactly this shape:\n"
        "{\n"
        '  "hypothesis": "<which metric is weak and why this change should help>",\n'
        '  "key": "<one key from learned_params>",\n'
        '  "old": <current value>,\n'
        '  "new": <proposed value, same type as old>,\n'
        '  "rationale": "<one or two sentences tying the change to the data>"\n'
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


def _normalize_key(key: str, current: dict[str, Any]) -> Optional[str]:
    """Map a near-miss key name onto the real learned_params key.

    LLMs occasionally hallucinate key variants (observed live:
    'confidence_threshold' for 'signal_confidence_threshold'). Rather than
    burning a whole review cycle on a name slip, accept a proposed key that
    unambiguously matches exactly one real key by substring; anything
    ambiguous or unmatched is still rejected.
    """
    if key in current:
        return key
    lowered = key.strip().lower()
    matches = [
        real for real in current
        if lowered in real.lower() or real.lower() in lowered
    ]
    return matches[0] if len(matches) == 1 else None


def _validate_delta(
    proposal: Optional[dict[str, Any]], current: dict[str, Any]
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    if not proposal:
        return None, "no JSON proposal parsed"
    key = proposal.get("key")
    if key is None:
        return None, proposal.get("rationale") or "reviewer declined to propose"
    normalized = _normalize_key(str(key), current)
    if normalized is None:
        return None, f"unknown key {key!r} not in learned_params"
    if normalized != key:
        logger.info("Reviewer proposed near-miss key %r; normalized to %r", key, normalized)
        proposal = {**proposal, "key": normalized}
    key = normalized
    old = proposal.get("old", current[key])
    new = proposal.get("new")
    if new is None:
        # LLMs sometimes rename the field (new_value, proposed, value…).
        # Accept an unambiguous alias rather than wasting the review cycle.
        for alias in ("new_value", "proposed", "proposed_value", "value", "to"):
            if proposal.get(alias) is not None:
                new = proposal[alias]
                logger.info("Reviewer proposal used %r for 'new'; accepted", alias)
                break
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
    holdout_frac = float(goals.get("walk_forward_holdout_frac", 0.3))

    since = datetime.now() - timedelta(days=window_days)
    all_rows = store.recent_decisions_with_outcomes(since=since, limit=10000)
    scoreboard = build_scoreboard(window_days, rows=all_rows)
    train_rows, holdout_rows = _split_rows(all_rows, holdout_frac)
    train_sb = build_scoreboard(window_days, rows=train_rows)
    holdout_sb = build_scoreboard(window_days, rows=holdout_rows)

    # Gate 1: enough total + per-slice evaluated decisions to learn anything.
    min_n = int(goals.get("min_decisions_for_review", 5))
    min_train = int(goals.get("min_train_decisions", 5))
    min_holdout = int(goals.get("min_holdout_decisions", 3))
    shortfall = None
    if scoreboard.n_evaluated < min_n:
        shortfall = f"insufficient data: {scoreboard.n_evaluated}/{min_n} evaluated decisions"
    elif train_sb.n_evaluated < min_train or holdout_sb.n_evaluated < min_holdout:
        shortfall = (
            f"insufficient data for walk-forward: train {train_sb.n_evaluated}/{min_train}, "
            f"holdout {holdout_sb.n_evaluated}/{min_holdout} evaluated decisions"
        )
    if shortfall is not None:
        # Record in DB so the Proposals tab shows the review ran (even if skipped).
        store.record_params_proposal(
            params=params_before, diff=None, rationale=shortfall, applied=False,
        )
        proposal_path = _write_proposal_md(
            goals, train_sb, holdout_sb, params_before, proposal=None,
            applied=False, reason=shortfall,
        )
        return ReviewResult(
            scoreboard=scoreboard, goals=goals, params_before=params_before,
            proposal=None, applied=False,
            rejection_reason=shortfall, proposal_path=proposal_path,
        )

    # Gate 2: ask the LLM to form a hypothesis on the TRAIN slice, avoiding
    # knobs we already tried and rejected.
    rejected_keys = _recently_rejected_keys()
    sample = train_rows[-15:][::-1]  # most-recent-first sample from the train slice
    raw = _ask_llm_for_delta(
        _build_prompt(goals, train_sb, holdout_sb, params_before, sample, rejected_keys)
    )
    parsed = _extract_json(raw or "")
    hypothesis = (parsed or {}).get("hypothesis") if isinstance(parsed, dict) else None
    proposal, rejection = _validate_delta(parsed, params_before)

    # Gate 3: knowledge guard — never re-apply a recently-rejected knob.
    if proposal is not None and proposal["key"] in rejected_keys:
        rejection = (
            f"knob {proposal['key']!r} was recently rejected: {rejected_keys[proposal['key']]}"
        )
        proposal = None

    # Gate 4: out-of-sample validation — only apply if the weakness is confirmed
    # on the holdout slice (don't chase train-window noise).
    validation_reason = None
    validated = False
    if proposal is not None:
        validated, validation_reason = _validation_verdict(train_sb, holdout_sb, goals)
        if not validated:
            rejection = validation_reason

    applied = False
    new_params = params_before
    if proposal is not None and validated and auto_apply:
        new_params = dict(params_before)
        new_params[proposal["key"]] = proposal["new"]
        learning_config.save_learned_params(new_params)
        applied = True

    # Persist hypothesis + validation + train/holdout context in the rationale so
    # the loop has a durable record of what was tried and why.
    if proposal is not None:
        rationale = proposal.get("rationale", "")
        parts = [p for p in (
            f"Hypothesis: {hypothesis}" if hypothesis else None,
            rationale or None,
            f"Validation: {validation_reason}" if validation_reason else None,
            f"(train win_rate={train_sb.win_rate}, holdout win_rate={holdout_sb.win_rate}, "
            f"train ic={train_sb.ic})",
        ) if p]
        recorded_rationale = " | ".join(parts)
    else:
        recorded_rationale = rejection

    diff = (
        {proposal["key"]: {"from": proposal["old"], "to": proposal["new"]}}
        if proposal else None
    )
    store.record_params_proposal(
        params=new_params, diff=diff, rationale=recorded_rationale, applied=applied,
    )

    proposal_path = _write_proposal_md(
        goals, train_sb, holdout_sb, params_before, proposal, applied,
        rejection, hypothesis=hypothesis,
    )
    return ReviewResult(
        scoreboard=scoreboard,
        goals=goals,
        params_before=params_before,
        proposal=proposal,
        applied=applied,
        rejection_reason=rejection if not applied else None,
        proposal_path=proposal_path,
    )


def _write_proposal_md(
    goals: dict[str, Any],
    train_sb: Scoreboard,
    holdout_sb: Scoreboard,
    params_before: dict[str, Any],
    proposal: Optional[dict[str, Any]],
    applied: bool,
    reason: Optional[str],
    hypothesis: Optional[str] = None,
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
        "## Train scoreboard (hypothesis formed here)",
        "```json",
        json.dumps(train_sb.to_dict(), indent=2),
        "```",
        "",
        "## Holdout scoreboard (validation slice)",
        "```json",
        json.dumps(holdout_sb.to_dict(), indent=2),
        "```",
        "",
        "## Current learned_params",
        "```json",
        json.dumps(params_before, indent=2),
        "```",
        "",
        "## Proposal",
    ]
    if hypothesis:
        lines += [f"**Hypothesis:** {hypothesis}", ""]
    if proposal:
        lines += [
            "```json",
            json.dumps(proposal, indent=2),
            "```",
            "",
            f"**Rationale:** {proposal.get('rationale', '')}",
        ]
        if reason:
            lines += ["", f"**Validation:** {reason}"]
    else:
        lines += [f"_None._ Reason: `{reason or 'unknown'}`"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
