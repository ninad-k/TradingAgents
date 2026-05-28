from __future__ import annotations

from typing import List

from .types import Bar, InstrumentSpec, PortfolioValuePoint, position_pnl


def buy_and_hold(bars: List[Bar], initial_capital: float,
                 spec: InstrumentSpec) -> List[PortfolioValuePoint]:
    """Equity curve of buying at the first bar's close and holding."""
    if not bars:
        return []
    entry = bars[0].close
    volume = initial_capital / entry if entry else 0.0
    out = []
    for bar in bars:
        pnl = position_pnl(spec, "BUY", entry, bar.close, volume)
        out.append(PortfolioValuePoint(date=bar.date, value=initial_capital + pnl))
    return out
