from __future__ import annotations

from .types import BacktestResult


def _fmt(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def render_summary(result: BacktestResult) -> str:
    c, m = result.config, result.metrics
    wins = sum(1 for t in result.trades if (t.pnl or 0) > 0)
    total_cost = sum((t.cost or 0.0) for t in result.trades)
    lines = [
        f"Backtest: {c.ticker}  {c.start_date} -> {c.end_date}  ({c.timeframe}, cadence={c.cadence_bars})",
        f"Initial capital: {c.initial_capital:,.2f}",
        f"Ending value:    {_fmt(m.ending_value)}",
        f"Total return:    {_fmt(m.total_return_pct)}%",
        f"Sharpe:          {_fmt(m.sharpe_ratio)}",
        f"Sortino:         {_fmt(m.sortino_ratio)}",
        f"Max drawdown:    {_fmt(m.max_drawdown)}%  ({m.max_drawdown_date or 'n/a'})",
        f"Trades: {len(result.trades)}  (wins: {wins})",
        f"Cost drag:       {total_cost:,.2f}  (commission + slippage round-trips)",
        f"Profit factor:   {_fmt(m.profit_factor)}",
        f"Expectancy:      {_fmt(m.expectancy)} per trade (net)",
        f"Validation:      {'PASS' if m.acceptance_passed else 'FAIL'}",
    ]
    if m.acceptance_reasons:
        lines.append("Validation notes: " + "; ".join(m.acceptance_reasons))
    if result.benchmark_values:
        bench = result.benchmark_values[-1].value
        lines.append(f"Buy & hold end:  {bench:,.2f}")
    return "\n".join(lines)
