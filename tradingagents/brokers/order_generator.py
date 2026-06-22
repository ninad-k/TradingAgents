"""
OrderGenerator: Convert TradingAgents decisions into MT5 orders.

Handles:
- Converting 5-tier ratings to trade actions
- Calculating lot size from position sizing %
- Computing risk management levels
- Calculating risk/reward ratios
"""

import logging
import os
from typing import Optional, Tuple
from datetime import datetime, timedelta

from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.brokers.models import (
    MT5Order, OrderAction, OrderType, SymbolInfo, AccountInfo, PendingOrder
)

logger = logging.getLogger(__name__)


class OrderGenerator:
    """Convert TradingAgents decisions to MT5 orders."""

    # Mapping from TradingAgents ratings to actions
    RATING_TO_ACTION = {
        PortfolioRating.BUY: OrderAction.BUY,
        PortfolioRating.OVERWEIGHT: OrderAction.BUY,
        PortfolioRating.HOLD: None,  # No action
        PortfolioRating.UNDERWEIGHT: OrderAction.SELL,
        PortfolioRating.SELL: OrderAction.SELL,
    }

    # Position sizing guidance per rating
    RATING_TO_SIZE_PERCENT = {
        PortfolioRating.BUY: 0.05,           # 5% of account
        PortfolioRating.OVERWEIGHT: 0.03,   # 3% of account
        PortfolioRating.HOLD: 0.0,          # No trade
        PortfolioRating.UNDERWEIGHT: 0.02,  # 2% of account (reduce)
        PortfolioRating.SELL: 0.05,         # 5% of account
    }

    def __init__(
        self,
        max_risk_percent: float = 2.0,
        max_risk_usd: Optional[float] = None,
        trade_comment: Optional[str] = None,
        fixed_lot_size: Optional[float] = None,
    ):
        """
        Initialize OrderGenerator.

        Args:
            max_risk_percent: Max % of account to risk per trade (default 2%)
            max_risk_usd: Max USD to risk per trade (optional, overrides percent)
            trade_comment: Comment string attached to the MT5 order
            fixed_lot_size: If explicitly set > 0, every BUY/SELL is sized at this
                many lots and the risk-based sizing math is bypassed entirely.
                Useful while per-symbol risk parameters are still being tuned.
                This is an explicit, per-instance opt-in only: it is intentionally
                NOT read from an ambient env var, because a globally-set override
                would silently defeat instrument-specific risk sizing (and the
                missing-pip-value guard) for every OrderGenerator in the process.
        """
        self.max_risk_percent = max_risk_percent
        self.max_risk_usd = max_risk_usd
        self.trade_comment = trade_comment or os.getenv("TRADINGAGENTS_TRADE_COMMENT", "TradingAgent2.0")
        self.fixed_lot_size = fixed_lot_size if (fixed_lot_size and fixed_lot_size > 0) else None
        if self.fixed_lot_size:
            logger.info("OrderGenerator: fixed lot override = %.3f lots/trade", self.fixed_lot_size)

    @staticmethod
    def _pip_value_per_lot(symbol_info: SymbolInfo) -> Optional[float]:
        """Account-currency value of a one-`point` move per 1.0 lot.

        Returns None when unavailable; callers MUST refuse to size rather than
        assume a value. Guessing (the old fixed 10.0 EURUSD default) mis-sizes
        real-money positions ~10x for non-EURUSD instruments such as XAUUSD.
        """
        pv = symbol_info.pip_value_per_lot
        if pv is None or pv <= 0:
            return None
        return pv

    def decision_to_order(
        self,
        decision: PortfolioDecision,
        symbol: str,
        symbol_info: SymbolInfo,
        account_info: AccountInfo,
        decision_id: str,
    ) -> Optional[MT5Order]:
        """
        Convert PortfolioDecision to MT5Order.

        Args:
            decision: TradingAgents PortfolioDecision
            symbol: Trading symbol (e.g., EURUSD, AAPL)
            symbol_info: Symbol specifications
            account_info: Current account state
            decision_id: Unique decision ID

        Returns:
            MT5Order ready to execute, or None if Hold decision
        """

        # Check if Hold decision
        if decision.rating == PortfolioRating.HOLD:
            logger.info(f"{symbol}: Hold decision, no trade generated")
            return None

        # Get action from rating
        action = self.RATING_TO_ACTION.get(decision.rating)
        if action is None:
            logger.warning(f"Unknown rating {decision.rating}, no trade generated")
            return None

        # Extract prices from decision
        entry_price = self._get_entry_price(decision, symbol_info, action)
        stop_loss = self._get_stop_loss(decision, symbol_info, action)
        take_profit = decision.price_target

        # Calculate position size
        volume = self._calculate_volume(
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            symbol_info=symbol_info,
            account_info=account_info,
        )

        if volume <= 0:
            logger.warning(f"Cannot calculate positive volume for {symbol}")
            return None

        # Create order
        order = MT5Order(
            symbol=symbol,
            action=action,
            volume=volume,
            order_type=OrderType.MARKET,  # Market order for immediate execution
            entry_price=entry_price if entry_price != symbol_info.bid and entry_price != symbol_info.ask else None,
            stop_loss=stop_loss,
            take_profit=take_profit,
            decision_id=decision_id,
            reason=decision.executive_summary,
            comment=self.trade_comment,
            # Risk management
            max_holding_time_hours=self._parse_time_horizon(decision.time_horizon),
            max_loss_per_trade=self._calculate_loss_amount(entry_price or symbol_info.ask, stop_loss, volume, symbol_info),
        )

        logger.info(
            f"Generated order: {action} {volume} {symbol} @ {entry_price} "
            f"SL={stop_loss} TP={take_profit}"
        )

        return order

    def _get_entry_price(
        self,
        decision: PortfolioDecision,
        symbol_info: SymbolInfo,
        action: OrderAction,
    ) -> float:
        """
        Get entry price from decision or use market price.

        Args:
            decision: PortfolioDecision with optional entry guidance
            symbol_info: Current bid/ask prices
            action: BUY or SELL

        Returns:
            Entry price for the order
        """
        # If decision specifies entry price, use it
        if decision.investment_thesis and "entry" in decision.investment_thesis.lower():
            # Could parse entry price from thesis, but for now use market
            pass

        # Use current market price (bid for sell, ask for buy)
        if action == OrderAction.BUY:
            return symbol_info.ask
        else:
            return symbol_info.bid

    def _get_stop_loss(
        self,
        decision: PortfolioDecision,
        symbol_info: SymbolInfo,
        action: OrderAction,
    ) -> Optional[float]:
        """
        Get stop loss price.

        Uses decision's stop loss or calculates from spread.

        Args:
            decision: PortfolioDecision
            symbol_info: Symbol specs including spread
            action: BUY or SELL

        Returns:
            Stop loss price or None
        """
        # For now, calculate a 2x spread stop loss
        # In production, would parse from decision
        spread_pips = symbol_info.spread
        stop_distance = max(spread_pips * 3, 20)  # At least 20 pips from entry

        if action == OrderAction.BUY:
            return symbol_info.bid - (stop_distance * symbol_info.point)
        else:
            return symbol_info.ask + (stop_distance * symbol_info.point)

    def _calculate_volume(
        self,
        action: OrderAction,
        entry_price: float,
        stop_loss: Optional[float],
        symbol_info: SymbolInfo,
        account_info: AccountInfo,
    ) -> float:
        """
        Calculate position size based on risk.

        Uses Kelly-like formula or fixed % of account.

        Args:
            action: BUY or SELL
            entry_price: Entry price
            stop_loss: Stop loss price (for risk calculation)
            symbol_info: Symbol specs
            account_info: Account equity

        Returns:
            Volume in lots
        """
        # Fixed-lot override: bypass risk math and clamp only to the broker's
        # volume_min/volume_max/volume_step so we always send a legal request.
        if self.fixed_lot_size:
            volume = self.fixed_lot_size
            volume = max(symbol_info.min_volume, min(volume, symbol_info.max_volume))
            volume = round(volume / symbol_info.volume_step) * symbol_info.volume_step
            return volume

        if not entry_price or not stop_loss:
            # If no stop loss, use fixed % of account
            size_percent = 0.02  # 2% default
            volume = (account_info.equity * size_percent) / entry_price
        else:
            # Risk-based sizing
            risk_pips = abs(entry_price - stop_loss) / symbol_info.point if symbol_info.point else 0

            if risk_pips <= 0:
                logger.warning("Invalid stop loss, using fixed 2% sizing")
                volume = (account_info.equity * 0.02) / entry_price
            else:
                # Calculate max risk in dollars
                if self.max_risk_usd:
                    max_risk = self.max_risk_usd
                else:
                    max_risk = account_info.equity * (self.max_risk_percent / 100)

                pip_value = self._pip_value_per_lot(symbol_info)
                if pip_value is None:
                    logger.error(
                        f"{symbol_info.symbol}: no pip_value_per_lot available; "
                        f"refusing to size. Populate SymbolInfo.pip_value_per_lot."
                    )
                    return 0.0
                # Volume = max_risk / (loss per lot at SL) = max_risk / (risk_pips * pip_value)
                volume = max_risk / (risk_pips * pip_value)

        # Respect symbol limits
        volume = max(symbol_info.min_volume, min(volume, symbol_info.max_volume))

        # Round to nearest volume step
        volume = round(volume / symbol_info.volume_step) * symbol_info.volume_step

        return volume

    def _calculate_loss_amount(
        self,
        entry_price: float,
        stop_loss: Optional[float],
        volume: float,
        symbol_info: SymbolInfo,
    ) -> Optional[float]:
        """
        Calculate maximum loss amount in USD.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            volume: Position volume
            symbol_info: Symbol specs

        Returns:
            Max loss in USD or None
        """
        if not stop_loss:
            return None

        pip_value = self._pip_value_per_lot(symbol_info)
        if pip_value is None:
            return None

        risk_pips = abs(entry_price - stop_loss) / symbol_info.point if symbol_info.point else 0

        return risk_pips * volume * pip_value

    def _parse_time_horizon(self, time_horizon: Optional[str]) -> Optional[int]:
        """
        Parse time horizon string to hours.

        Args:
            time_horizon: String like "3-6 months", "1 week", "1 day"

        Returns:
            Hours to hold position, or None
        """
        if not time_horizon:
            return None

        time_horizon_lower = time_horizon.lower()

        # Parse time horizon
        if "day" in time_horizon_lower:
            return 24
        elif "week" in time_horizon_lower:
            return 24 * 7
        elif "month" in time_horizon_lower:
            return 24 * 30
        elif "hour" in time_horizon_lower:
            try:
                hours = int(time_horizon_lower.split()[0])
                return hours
            except:
                return 24

        return None  # Unknown format

    def propose_order(
        self,
        decision: PortfolioDecision,
        symbol: str,
        symbol_info: SymbolInfo,
        account_info: AccountInfo,
        decision_id: str,
    ) -> Optional[PendingOrder]:
        """
        Generate a PendingOrder for user approval.

        Args:
            decision: TradingAgents decision
            symbol: Trading symbol
            symbol_info: Symbol specs
            account_info: Account state
            decision_id: Decision ID

        Returns:
            PendingOrder ready for user review
        """
        # Generate MT5Order
        order = self.decision_to_order(
            decision=decision,
            symbol=symbol,
            symbol_info=symbol_info,
            account_info=account_info,
            decision_id=decision_id,
        )

        if order is None:
            return None

        # Calculate risk metrics
        risk_per_trade = order.max_loss_per_trade or 0
        reward_target = None
        risk_reward_ratio = None

        pip_value = self._pip_value_per_lot(symbol_info)
        if order.take_profit and order.entry_price and pip_value is not None:
            reward_pips = abs(order.take_profit - order.entry_price) / symbol_info.point
            reward_target = reward_pips * order.volume * pip_value

            if risk_per_trade and risk_per_trade > 0:
                risk_reward_ratio = reward_target / risk_per_trade

        # Create pending order
        pending = PendingOrder(
            pending_id=f"{decision_id}:{symbol}:{datetime.utcnow().timestamp()}",
            order=order,
            account_info=account_info,
            symbol_info=symbol_info,
            risk_per_trade=risk_per_trade,
            reward_target=reward_target,
            risk_reward_ratio=risk_reward_ratio,
            decision_reasoning=decision.investment_thesis,
        )

        logger.info(f"Proposed order: {pending.pending_id}")
        return pending
