"""BacktestEngine: bar-loop with t+1 fills and SL/TP/TIME/EOD exits."""
from __future__ import annotations

from typing import Optional

from .benchmarks import buy_and_hold
from .data import BarProvider
from .metrics import PerformanceMetricsCalculator
from .portfolio import Portfolio
from .types import (
    BacktestConfig,
    BacktestResult,
    Bar,
    InstrumentSpec,
    OrderIntent,
    PortfolioValuePoint,
)


class BacktestEngine:
    """Single-instrument bar loop.

    Entries fill at the next bar's open; SL/TP are checked intrabar on
    SUBSEQUENT bars (SL takes priority when a bar hits both); a position
    is held until SL/TP, a bar-count time-stop, or end-of-data.

    A new decision is requested only on a rebalance bar (every ``cadence_bars``
    bars) AND only while flat. While a position is open, intervening rebalance
    bars are skipped, so the effective time between entries is at least
    ``cadence_bars`` bars and longer whenever a position is held across one.
    """

    def __init__(
        self,
        *,
        config: BacktestConfig,
        provider: BarProvider,
        spec: InstrumentSpec,
        controller,
        position_model,
    ) -> None:
        self._config = config
        self._provider = provider
        self._spec = spec
        self._controller = controller
        self._position_model = position_model

    def _hours_to_bars(self, hours: Optional[int]) -> Optional[int]:
        if not hours:
            return None
        if self._config.timeframe == "1d":
            return max(1, hours // 24)
        if self._config.timeframe == "1h":
            return max(1, hours)
        if self._config.timeframe == "4h":
            return max(1, hours // 4)
        return None

    def run(self) -> BacktestResult:
        cfg = self._config
        bars = self._provider.get_bars(
            cfg.ticker, cfg.start_date, cfg.end_date, cfg.timeframe
        )

        portfolio = Portfolio(cfg.initial_capital, self._spec)
        values: list[PortfolioValuePoint] = []
        trades = []
        pending: Optional[OrderIntent] = None
        bars_held: int = 0
        calculator = PerformanceMetricsCalculator(annual_trading_days=cfg.annual_trading_days)

        for i, bar in enumerate(bars):
            filled_this_bar = False
            # 1) Fill a pending entry at this bar's open.
            if pending is not None and portfolio.is_flat():
                portfolio.open(side=pending.side, date=bar.date, price=bar.open,
                               volume=pending.volume, stop_loss=pending.stop_loss,
                               take_profit=pending.take_profit,
                               max_holding_hours=pending.max_holding_hours)
                bars_held = 0
                pending = None
                filled_this_bar = True

            # 2) Manage an open position only on bars AFTER the entry bar, so a
            #    position can never enter and exit within the same bar (no look-ahead).
            if not portfolio.is_flat() and not filled_this_bar:
                bars_held += 1
                exit_result = self._check_exit(portfolio.open_trade, bar, bars_held)
                if exit_result is not None:
                    exit_price, reason = exit_result
                    trade = portfolio.close(bar.date, exit_price, reason)
                    trades.append(trade)
                    bars_held = 0

            # 3. Rebalance while flat on cadence
            if portfolio.is_flat() and (i % cfg.cadence_bars == 0):
                equity = portfolio.equity(bar.close)
                decision = self._controller.decide(cfg.ticker, bar.date)
                intent = self._position_model.build_order(decision, self._spec, bar, equity)
                if intent is not None:
                    pending = intent

            # 4. Record equity at bar close
            values.append(PortfolioValuePoint(date=bar.date, value=portfolio.equity(bar.close)))

        # 5. Force-close any open position at last bar's close
        if bars and not portfolio.is_flat():
            last = bars[-1]
            trade = portfolio.close(last.date, last.close, "EOD")
            trades.append(trade)
            # Update the last value point with the closed equity
            values[-1] = PortfolioValuePoint(date=last.date, value=portfolio.equity(last.close))

        metrics = calculator.compute_metrics(values)
        benchmark = buy_and_hold(bars, cfg.initial_capital, self._spec)

        return BacktestResult(
            config=cfg,
            values=values,
            trades=trades,
            metrics=metrics,
            benchmark_values=benchmark,
        )

    def _check_exit(self, trade, bar: Bar, bars_held: int) -> Optional[tuple]:
        """Return (exit_price, reason) if the bar triggers an exit, else None."""
        long = trade.side == "BUY"
        # SL first (worst case) when both could trigger in one bar.
        if trade.stop_loss is not None:
            if long and bar.low <= trade.stop_loss:
                return (min(bar.open, trade.stop_loss), "SL")
            if not long and bar.high >= trade.stop_loss:
                return (max(bar.open, trade.stop_loss), "SL")
        if trade.take_profit is not None:
            if long and bar.high >= trade.take_profit:
                return (max(bar.open, trade.take_profit), "TP")
            if not long and bar.low <= trade.take_profit:
                return (min(bar.open, trade.take_profit), "TP")
        max_bars = self._hours_to_bars(trade.max_holding_hours)
        if max_bars is not None and bars_held >= max_bars:
            return (bar.close, "TIME")
        return None
