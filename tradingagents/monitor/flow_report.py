"""Render a completed analysis flow into a management-ready Markdown report.

The scheduler already persists the full multi-agent trace (every analyst,
both debate transcripts, the trader plan, the risk panel, the final decision,
and the execution result) via ``store.save_analysis_trace``. This module turns
one such trace into a human-readable report that can be handed to management,
and maintains a rolling one-line-per-decision summary for a session overview.

Markdown is the canonical format (no heavy dependencies). A caller that wants a
PDF can convert the Markdown downstream.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Human labels + render order for the 12 pipeline components.
_COMPONENT_LABELS = [
    ("market_analyst", "Market Analyst"),
    ("sentiment_analyst", "Social / Sentiment Analyst"),
    ("news_analyst", "News Analyst"),
    ("fundamentals_analyst", "Fundamentals Analyst"),
    ("bull_researcher", "Bull Researcher"),
    ("bear_researcher", "Bear Researcher"),
    ("research_manager", "Research Manager (verdict)"),
    ("trader", "Trader (plan)"),
    ("aggressive_risk", "Aggressive Risk"),
    ("neutral_risk", "Neutral Risk"),
    ("conservative_risk", "Conservative Risk"),
    ("portfolio_manager", "Portfolio Manager (final decision)"),
]


def report_dir(config: Optional[Dict[str, Any]] = None) -> Path:
    """Directory where per-flow reports and the rolling summary live."""
    from tradingagents.default_config import DEFAULT_CONFIG

    results_dir = (config or DEFAULT_CONFIG).get("results_dir") or DEFAULT_CONFIG["results_dir"]
    path = Path(results_dir) / "flow_reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _section(title: str, body: Any) -> str:
    text = (str(body).strip() if body is not None else "")
    if not text:
        text = "_No output captured._"
    return f"### {title}\n\n{text}\n"


def _render_execution(execution: Optional[Dict[str, Any]]) -> str:
    if not execution:
        return "_No trade executed for this decision._"
    rows = []
    for key in ("status", "reason", "ticket", "execution_price", "comment"):
        if key in execution and execution[key] is not None:
            rows.append(f"- **{key.replace('_', ' ').title()}**: {execution[key]}")
    return "\n".join(rows) if rows else f"- {execution}"


def render_flow_report(
    trace: Dict[str, Any],
    *,
    decision_id: Optional[int] = None,
    confidence: Optional[float] = None,
    trading_mode: Optional[str] = None,
) -> str:
    """Render one analysis trace into a Markdown report string."""
    components = trace.get("components", {}) or {}
    debates = trace.get("debates", {}) or {}
    symbol = trace.get("symbol", "?")
    signal = trace.get("signal", "?")
    timestamp = trace.get("timestamp", "")
    success = trace.get("success", False)

    lines = [
        f"# Analysis Flow Report — {symbol}",
        "",
        "## Summary",
        "",
        f"- **Symbol**: {symbol}",
        f"- **Signal**: {signal}",
        f"- **Timestamp**: {timestamp}",
        f"- **Successful run**: {'yes' if success else 'no'}",
    ]
    if decision_id is not None:
        lines.append(f"- **Decision ID**: {decision_id}")
    if confidence is not None:
        lines.append(f"- **Confidence**: {confidence}")
    if trading_mode:
        lines.append(f"- **Trading mode**: {trading_mode}")
    lines.append("")

    lines.append("## Agent Pipeline")
    lines.append("")
    for key, label in _COMPONENT_LABELS:
        lines.append(_section(label, components.get(key)))

    lines.append("## Debate Transcripts")
    lines.append("")
    lines.append(_section("Research Debate (Bull vs Bear)", debates.get("research")))
    lines.append(_section("Risk Debate", debates.get("risk")))

    lines.append("## Execution")
    lines.append("")
    lines.append(_render_execution(trace.get("execution")))
    lines.append("")

    return "\n".join(lines)


def _summary_line(trace: Dict[str, Any], decision_id: Optional[int], execution: Optional[Dict[str, Any]]) -> str:
    status = (execution or {}).get("status", "-") if execution else "-"
    return (
        f"| {trace.get('timestamp', '')} "
        f"| {trace.get('symbol', '?')} "
        f"| {trace.get('signal', '?')} "
        f"| {decision_id if decision_id is not None else '-'} "
        f"| {status} |"
    )


def append_management_summary(
    trace: Dict[str, Any],
    decision_id: Optional[int],
    execution: Optional[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Path:
    """Append one row to the rolling management summary table."""
    path = report_dir(config) / "management_summary.md"
    header = "| Timestamp | Symbol | Signal | Decision | Execution |\n|---|---|---|---|---|\n"
    if not path.exists():
        path.write_text("# Management Summary — Trading Flow\n\n" + header, encoding="utf-8")
    with open(path, "a", encoding="utf-8") as f:
        f.write(_summary_line(trace, decision_id, execution) + "\n")
    return path


def write_flow_report(
    config: Dict[str, Any],
    result: Any,
    trace: Dict[str, Any],
    decision_id: Optional[int],
) -> Optional[Path]:
    """Render + persist a per-flow report and append the management summary.

    Best-effort: returns the report path, or None on failure (never raises so a
    reporting hiccup can't abort a trading run).
    """
    try:
        symbol = str(trace.get("symbol", "unknown")).upper()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        did = decision_id if decision_id is not None else "na"
        fname = f"{symbol}_{did}_{stamp}.md"
        md = render_flow_report(
            trace,
            decision_id=decision_id,
            trading_mode=str(config.get("trading_mode", "")) or None,
        )
        path = report_dir(config) / fname
        path.write_text(md, encoding="utf-8")
        append_management_summary(trace, decision_id, getattr(result, "execution", None), config)
        logger.info("Flow report written: %s", path)
        return path
    except Exception:
        logger.warning("Failed to write flow report", exc_info=True)
        return None
