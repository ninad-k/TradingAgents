"""
`tradingagents learning ...` — drive the self-improvement loop from the CLI.

Read commands (decisions, proposals, params) are safe to run anywhere.
Write commands (review, outcomes) actually mutate the store + filesystem,
so they share the same SQLite DB the dashboard process uses.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich import box

learning_app = typer.Typer(
    name="learning",
    help="Self-improvement learning loop (decisions, outcomes, reviewer proposals).",
    add_completion=False,
)

console = Console()


def _fmt_ts(value: Optional[str]) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return value


def _fmt_float(value, digits: int = 4) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


@learning_app.command("decisions")
def cli_decisions(
    limit: int = typer.Option(20, help="Max rows to show."),
    symbol: Optional[str] = typer.Option(None, help="Filter by symbol."),
    since_days: Optional[int] = typer.Option(None, help="Only decisions in the last N days."),
) -> None:
    """Show recent decisions joined with outcomes."""
    from tradingagents.monitor import store
    from datetime import timedelta

    since = datetime.now() - timedelta(days=since_days) if since_days else None
    rows = store.recent_decisions_with_outcomes(since=since, limit=limit)
    if symbol:
        sym = symbol.upper()
        rows = [r for r in rows if (r.get("symbol") or "").upper() == sym]

    if not rows:
        console.print("[dim]No decisions in window.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAVY, title=f"Decisions ({len(rows)})")
    table.add_column("id", justify="right")
    table.add_column("decided_at")
    table.add_column("symbol")
    table.add_column("signal")
    table.add_column("entry", justify="right")
    table.add_column("exit", justify="right")
    table.add_column("pnl_pct", justify="right")
    table.add_column("evaluated_at")
    for r in rows:
        pnl = r.get("pnl_pct")
        pnl_str = _fmt_float(pnl, 2)
        style = "green" if pnl and pnl > 0 else ("red" if pnl and pnl < 0 else "")
        table.add_row(
            str(r.get("id", "")),
            _fmt_ts(r.get("decided_at")),
            r.get("symbol", "") or "",
            r.get("signal", "") or "",
            _fmt_float(r.get("entry_price"), 5),
            _fmt_float(r.get("exit_price"), 5),
            f"[{style}]{pnl_str}[/{style}]" if style else pnl_str,
            _fmt_ts(r.get("evaluated_at")),
        )
    console.print(table)


@learning_app.command("outcomes")
def cli_outcomes(
    limit: int = typer.Option(100, help="Max pending decisions to evaluate."),
) -> None:
    """Evaluate any decisions whose horizon has elapsed."""
    from tradingagents.monitor import outcomes

    console.print("Evaluating pending decisions…")
    n = outcomes.evaluate_pending(limit=limit)
    console.print(f"Processed [bold]{n}[/bold] decision(s).")


@learning_app.command("review")
def cli_review(
    window_days: Optional[int] = typer.Option(
        None, help="Override the scoreboard window (defaults to goals.json)."
    ),
    auto_apply: bool = typer.Option(
        False, "--auto-apply", help="Apply the proposal immediately if valid."
    ),
) -> None:
    """Run the reviewer once and print the result."""
    from tradingagents.monitor import reviewer

    # window_days override is handled inside run_review via goals; for now just respect default.
    if window_days is not None:
        console.print(
            f"[yellow]Note: --window-days currently uses goals.json review_window_days "
            f"({window_days} ignored).[/yellow]"
        )

    result = reviewer.run_review(auto_apply=auto_apply)
    console.print(Panel.fit(
        f"applied=[bold]{result.applied}[/bold]  "
        f"rejection=[yellow]{result.rejection_reason or '—'}[/yellow]\n"
        f"proposal_path={result.proposal_path}",
        title="Reviewer result",
    ))

    if result.proposal:
        table = Table(box=box.SIMPLE)
        table.add_column("key"); table.add_column("old"); table.add_column("new")
        table.add_row(
            result.proposal["key"],
            str(result.proposal["old"]),
            str(result.proposal["new"]),
        )
        console.print(table)
        console.print(f"[dim]Rationale:[/dim] {result.proposal.get('rationale', '')}")

    sb = result.scoreboard.to_dict()
    console.print(Panel.fit(
        f"n_evaluated={sb['n_evaluated']}  "
        f"win_rate={_fmt_float(sb['win_rate'], 3)}  "
        f"mean_pnl_pct={_fmt_float(sb['mean_pnl_pct'], 3)}  "
        f"sharpe={_fmt_float(sb['sharpe'], 3)}",
        title="Scoreboard",
    ))


@learning_app.command("proposals")
def cli_proposals(
    status: str = typer.Option("pending", help="pending|applied|rejected|all"),
    limit: int = typer.Option(10, help="Max rows."),
    show_md: bool = typer.Option(False, "--show-md", help="Render the proposal markdown."),
) -> None:
    """List reviewer proposals."""
    from tradingagents.monitor import store, reviewer

    if status not in {"pending", "applied", "rejected", "all"}:
        console.print(f"[red]Invalid status: {status}[/red]")
        raise typer.Exit(code=1)

    rows = store.list_proposals(status=status, limit=limit)
    if not rows:
        console.print(f"[dim]No {status} proposals.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAVY, title=f"Proposals — {status} ({len(rows)})")
    table.add_column("id", justify="right")
    table.add_column("proposed_at")
    table.add_column("key")
    table.add_column("from→to")
    table.add_column("status")
    table.add_column("rationale", overflow="fold")
    for p in rows:
        diff = p.get("diff") or {}
        key = next(iter(diff), "")
        if key:
            from_to = f"{diff[key].get('from')} → {diff[key].get('to')}"
        else:
            from_to = "—"
        if p["applied"]:
            st = "[green]applied[/green]"
        elif p.get("rejected_at"):
            st = "[red]rejected[/red]"
        else:
            st = "[yellow]pending[/yellow]"
        table.add_row(
            str(p["id"]), _fmt_ts(p["proposed_at"]), key, from_to, st,
            (p.get("rationale") or "")[:120],
        )
    console.print(table)

    if show_md and reviewer.PROPOSALS_DIR.exists():
        mds = sorted(reviewer.PROPOSALS_DIR.glob("*.md"))[-3:]
        for path in mds:
            console.print(Panel(Markdown(path.read_text(encoding="utf-8")), title=path.name))


@learning_app.command("params")
def cli_params() -> None:
    """Show the live learned_params.json and goals.json."""
    from tradingagents.monitor import learning_config

    params = learning_config.load_learned_params()
    goals = learning_config.load_goals()
    console.print(Panel(
        json.dumps(params, indent=2, sort_keys=True),
        title=f"learned_params.json ({learning_config.learned_params_path()})",
    ))
    console.print(Panel(
        json.dumps(goals, indent=2, sort_keys=True),
        title=f"goals.json ({learning_config.goals_path()})",
    ))
