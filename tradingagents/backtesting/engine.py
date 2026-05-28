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
    """Single-symbol bar-loop backtest.

    Fill logic:
    - When flat and a decision arrives (every cadence_bars bars), the engine
      stores a pending OrderIntent.
    - The pending entry is filled at the *next* bar's open (t+1 fill).

    Exit logic (_check_exit, checked at each bar while a position is open):
    - SL checked first: if low <= stop_loss → exit at min(open, stop_loss).
    - TP checked second: if high >= take_profit → exit at max(open, take_profit).
    - TIME: if max_holding_hours set and elapsed >= threshold → exit at close.
    - EOD: any position still open at the last bar is closed at that bar's close.
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

    def run(self) -> BacktestResult:
        cfg = self._config
        bars = self._provider.get_bars(
            cfg.ticker, cfg.start_date, cfg.end_date, cfg.timeframe
        )

        portfolio = Portfolio(cfg.initial_capital, self._spec)
        values: list[PortfolioValuePoint] = []
        trades = []
        pending: Optional[OrderIntent] = None
        calculator = PerformanceMetricsCalculator(annual_trading_days=cfg.annual_trading_days)

        for i, bar in enumerate(bars):
            # 1. Fill pending entry at this bar's open (t+1 from the decide bar)
            if pending is not None and portfolio.is_flat():
                portfolio.open(
                    side=pending.side,
                    date=bar.date,
                    price=bar.open,
                    volume=pending.volume,
                    stop_loss=pending.stop_loss,
                    take_profit=pending.take_profit,
                    max_holding_hours=pending.max_holding_hours,
                )
                pending = None

            # 2. Manage open position: check SL → TP → TIME
            if not portfolio.is_flat():
                exit_result = self._check_exit(portfolio.open_trade, bar)
                if exit_result is not None:
                    exit_price, reason = exit_result
                    trade = portfolio.close(bar.date, exit_price, reason)
                    trades.append(trade)

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

    @staticmethod
    def _check_exit(trade, bar: Bar):
        """Return (exit_price, reason) or None. SL evaluated before TP."""
        sl = trade.stop_loss
        tp = trade.take_profit

        if trade.side == "BUY":
            # SL first
            if sl is not None and bar.low <= sl:
                return (min(bar.open, sl), "SL")
            # TP second
            if tp is not None and bar.high >= tp:
                return (max(bar.open, tp), "TP")
        else:  # SELL / short
            # SL first (price rises against short)
            if sl is not None and bar.high >= sl:
                return (max(bar.open, sl), "SL")
            # TP second (price falls in favour of short)
            if tp is not None and bar.low <= tp:
                return (min(bar.open, tp), "TP")

        # TIME exit: treat max_holding_hours as bars (daily bars ≈ 24 h each)
        if trade.max_holding_hours is not None:
            from datetime import datetime
            try:
                entry_dt = datetime.strptime(trade.entry_date, "%Y-%m-%d")
                bar_dt = datetime.strptime(bar.date, "%Y-%m-%d")
                elapsed_hours = (bar_dt - entry_dt).total_seconds() / 3600
                if elapsed_hours >= trade.max_holding_hours:
                    return (bar.close, "TIME")
            except ValueError:
                pass

        return None
