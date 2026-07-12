from __future__ import annotations

from typing import Optional

from .types import InstrumentSpec, Trade, position_pnl, trade_cost


class Portfolio:
    """Single open position with PnL-based equity: initial + realized + unrealized."""

    def __init__(self, initial_capital: float, spec: InstrumentSpec) -> None:
        self.initial_capital = float(initial_capital)
        self.spec = spec
        self.realized_pnl = 0.0
        self.open_trade: Optional[Trade] = None

    def is_flat(self) -> bool:
        return self.open_trade is None

    def open(self, side: str, date: str, price: float, volume: float,
             stop_loss=None, take_profit=None, max_holding_hours=None) -> Trade:
        if self.open_trade is not None:
            raise RuntimeError("position already open")
        entry_cost = trade_cost(self.spec, price, volume)
        self.open_trade = Trade(
            symbol=self.spec.symbol, side=side, entry_date=date,
            entry_price=price, volume=volume, stop_loss=stop_loss,
            take_profit=take_profit, max_holding_hours=max_holding_hours,
            entry_cost=entry_cost,
        )
        # Entry commission is paid immediately, so equity reflects it while held.
        self.realized_pnl -= entry_cost
        return self.open_trade

    def unrealized(self, current_price: float) -> float:
        t = self.open_trade
        if t is None:
            return 0.0
        return position_pnl(self.spec, t.side, t.entry_price, current_price, t.volume)

    def equity(self, current_price: float) -> float:
        return self.initial_capital + self.realized_pnl + self.unrealized(current_price)

    def close(self, date: str, price: float, reason: str) -> Trade:
        t = self.open_trade
        if t is None:
            raise RuntimeError("no open position")
        t.exit_date = date
        t.exit_price = price
        t.exit_reason = reason
        gross = position_pnl(self.spec, t.side, t.entry_price, price, t.volume)
        exit_cost = trade_cost(self.spec, price, t.volume)
        t.gross_pnl = gross
        t.cost = t.entry_cost + exit_cost
        t.pnl = gross - t.cost                      # net of round-trip commission
        # entry_cost was already deducted at open(); here add gross less exit cost.
        self.realized_pnl += gross - exit_cost
        self.open_trade = None
        return t
