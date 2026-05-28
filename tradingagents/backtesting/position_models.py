from __future__ import annotations

from typing import Optional, Protocol

from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.brokers.models import AccountInfo, OrderAction, SymbolInfo
from tradingagents.brokers.order_generator import OrderGenerator

from .types import Bar, InstrumentKind, InstrumentSpec, OrderIntent

_BUY_RATINGS = {PortfolioRating.BUY, PortfolioRating.OVERWEIGHT}
_SELL_RATINGS = {PortfolioRating.SELL, PortfolioRating.UNDERWEIGHT}


class PositionModel(Protocol):
    def build_order(self, decision: PortfolioDecision, spec: InstrumentSpec,
                    bar: Bar, equity: float) -> Optional[OrderIntent]:
        ...


class EquitySharesModel:
    """Share-based sizing as a fraction of current equity.

    Note: intentionally emits no stop-loss in v1 (``stop_loss=None``); position
    exits rely on take-profit and the engine's time/EOD handling.

    For equities a Sell/Underweight opens a short with no stop-loss (the shares
    model emits ``stop_loss=None``); such a short is only closed by its
    take-profit (if reachable) or the engine's end-of-data force-close — a v1
    simplification (no margin/borrow modeling).
    """

    def __init__(self, buy_fraction: float = 0.05, reduce_fraction: float = 0.03) -> None:
        self.buy_fraction = buy_fraction
        self.reduce_fraction = reduce_fraction

    def build_order(self, decision, spec, bar, equity) -> Optional[OrderIntent]:
        if decision.rating in _BUY_RATINGS:
            side = "BUY"
        elif decision.rating in _SELL_RATINGS:
            side = "SELL"
        else:
            return None
        frac = self.buy_fraction if decision.rating in (PortfolioRating.BUY, PortfolioRating.SELL) else self.reduce_fraction
        notional = equity * frac
        volume = int(notional / bar.close) if bar.close > 0 else 0
        if volume <= 0:
            return None
        return OrderIntent(side=side, volume=float(volume), entry_price=bar.close,
                           stop_loss=None, take_profit=decision.price_target)


class ForexLotModel:
    """Wraps the live OrderGenerator so the backtest exercises deploy sizing/SL/TP.

    Lot sizing uses the instrument's ``pip_value_per_lot`` (threaded into
    ``SymbolInfo``), so absolute lot sizes are instrument-specific and match the
    PnL economics applied by ``position_pnl``.
    """

    def __init__(self, max_risk_percent: float = 2.0) -> None:
        self._gen = OrderGenerator(max_risk_percent=max_risk_percent)

    def _symbol_info(self, spec: InstrumentSpec, bar: Bar) -> SymbolInfo:
        spread_price = spec.spread_points * spec.point
        return SymbolInfo(
            symbol=spec.symbol, bid=bar.close, ask=bar.close + spread_price,
            spread=spec.spread_points, digits=2, point=spec.point,
            min_volume=spec.min_volume, max_volume=spec.max_volume,
            volume_step=spec.volume_step, pip_value_per_lot=spec.pip_value_per_lot,
        )

    def _account_info(self, equity: float) -> AccountInfo:
        return AccountInfo(
            login=0, server="backtest", account_type="DEMO", currency="USD",
            balance=equity, equity=equity, free_margin=equity, margin_level=1000.0,
        )

    def build_order(self, decision, spec, bar, equity) -> Optional[OrderIntent]:
        order = self._gen.decision_to_order(
            decision=decision, symbol=spec.symbol,
            symbol_info=self._symbol_info(spec, bar),
            account_info=self._account_info(equity),
            decision_id=f"bt:{spec.symbol}:{bar.date}",
        )
        if order is None:
            return None
        side = "BUY" if order.action == OrderAction.BUY else "SELL"
        entry = order.entry_price or (bar.close + spec.spread_points * spec.point
                                      if side == "BUY" else bar.close)
        return OrderIntent(side=side, volume=order.volume, entry_price=entry,
                           stop_loss=order.stop_loss, take_profit=order.take_profit,
                           max_holding_hours=order.max_holding_time_hours)
