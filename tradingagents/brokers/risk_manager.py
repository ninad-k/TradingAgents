"""
RiskManager: Enforce risk limits and manage open positions.

Handles:
- Daily loss limits
- Maximum drawdown limits
- Position count limits
- Trailing stops
- Time-based position exits
- Risk validation before orders
"""

import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from tradingagents.brokers.models import (
    MT5Order, Position, AccountInfo, RiskLimits
)

logger = logging.getLogger(__name__)


class RiskManager:
    """Manage trading risk and enforce limits."""

    def __init__(
        self,
        max_daily_loss: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        max_open_positions: int = 5,
        trailing_stop_distance: Optional[float] = None,
        max_risk_per_trade_percent: float = 2.0,
        max_risk_per_trade_usd: Optional[float] = None,
    ):
        """
        Initialize RiskManager.

        Args:
            max_daily_loss: Max loss per day in USD
            max_drawdown: Max drawdown in USD
            max_open_positions: Max number of open positions
            trailing_stop_distance: Default trailing stop in pips
            max_risk_per_trade_percent: Max % of account per trade
            max_risk_per_trade_usd: Max USD per trade
        """
        self.limits = RiskLimits(
            max_daily_loss=max_daily_loss,
            max_drawdown=max_drawdown,
            max_open_positions=max_open_positions,
            trailing_stop_distance=trailing_stop_distance,
            max_risk_per_trade_percent=max_risk_per_trade_percent,
            max_risk_per_trade_usd=max_risk_per_trade_usd,
        )

        # Track daily starting balance for daily loss calculation
        self._daily_start_balance: Optional[float] = None
        self._daily_start_time: Optional[datetime] = None
        self._peak_equity: Optional[float] = None

    def can_open_trade(
        self,
        order: MT5Order,
        account_info: AccountInfo,
        open_positions: List[Position],
    ) -> tuple[bool, str]:
        """
        Check if new order respects all risk limits.

        Args:
            order: Order to check
            account_info: Current account state
            open_positions: List of open positions

        Returns:
            (allowed: bool, message: str)
        """
        checks = []

        # Check 1: Position count
        if len(open_positions) >= self.limits.max_open_positions:
            msg = f"Max open positions ({self.limits.max_open_positions}) reached"
            logger.warning(msg)
            checks.append((False, msg))
        else:
            checks.append((True, "Position count OK"))

        # Check 2: Daily loss limit
        if self.limits.max_daily_loss:
            daily_loss_check = self._check_daily_loss(account_info)
            checks.append(daily_loss_check)

        # Check 3: Drawdown limit
        if self.limits.max_drawdown:
            drawdown_check = self._check_drawdown(account_info)
            checks.append(drawdown_check)

        # Check 4: Margin available
        margin_check = self._check_margin(order, account_info)
        checks.append(margin_check)

        # Check 5: Risk per trade
        risk_check = self._check_risk_per_trade(order, account_info)
        checks.append(risk_check)

        # All checks must pass
        all_passed = all(check[0] for check in checks)
        messages = [msg for _, msg in checks]

        return all_passed, "; ".join(messages)

    def _check_daily_loss(self, account_info: AccountInfo) -> tuple[bool, str]:
        """Check daily loss limit."""
        if not self.limits.max_daily_loss:
            return (True, "Daily loss limit not set")

        # Initialize daily tracking on first call
        now = datetime.utcnow()
        if self._daily_start_time is None or self._is_new_trading_day(now):
            self._daily_start_balance = account_info.balance
            self._daily_start_time = now

        # Calculate daily loss
        daily_loss = self._daily_start_balance - account_info.balance
        remaining = self.limits.max_daily_loss - daily_loss

        if daily_loss >= self.limits.max_daily_loss:
            msg = f"Daily loss limit reached (${daily_loss:.2f} / ${self.limits.max_daily_loss:.2f})"
            logger.warning(msg)
            return (False, msg)
        else:
            msg = f"Daily loss: ${daily_loss:.2f} (${remaining:.2f} remaining)"
            return (True, msg)

    def _check_drawdown(self, account_info: AccountInfo) -> tuple[bool, str]:
        """Check maximum drawdown limit."""
        if not self.limits.max_drawdown:
            return (True, "Drawdown limit not set")

        # Track peak equity
        if self._peak_equity is None or account_info.equity > self._peak_equity:
            self._peak_equity = account_info.equity

        # Calculate drawdown
        drawdown = self._peak_equity - account_info.equity
        remaining = self.limits.max_drawdown - drawdown

        if drawdown >= self.limits.max_drawdown:
            msg = f"Max drawdown limit reached (${drawdown:.2f} / ${self.limits.max_drawdown:.2f})"
            logger.warning(msg)
            return (False, msg)
        else:
            msg = f"Drawdown: ${drawdown:.2f} (${remaining:.2f} remaining)"
            return (True, msg)

    def _check_margin(self, order: MT5Order, account_info: AccountInfo) -> tuple[bool, str]:
        """Check if enough free margin for order."""
        # Simplified margin check: rough estimate
        # In production, would use precise pip value and leverage
        required_margin = order.volume * 1000  # Rough estimate

        if required_margin > account_info.free_margin:
            msg = f"Insufficient margin (need ${required_margin:.2f}, have ${account_info.free_margin:.2f})"
            logger.warning(msg)
            return (False, msg)
        else:
            msg = f"Margin available: ${account_info.free_margin:.2f}"
            return (True, msg)

    def _check_risk_per_trade(self, order: MT5Order, account_info: AccountInfo) -> tuple[bool, str]:
        """Check risk per trade limits."""
        risk_amount = order.max_loss_per_trade or 0

        if not risk_amount:
            return (True, "No stop loss, risk amount unknown")

        # Check % of account
        risk_percent = (risk_amount / account_info.equity) * 100
        if risk_percent > self.limits.max_risk_per_trade_percent:
            msg = f"Risk too high ({risk_percent:.2f}% > {self.limits.max_risk_per_trade_percent}%)"
            logger.warning(msg)
            return (False, msg)

        # Check USD amount
        if self.limits.max_risk_per_trade_usd and risk_amount > self.limits.max_risk_per_trade_usd:
            msg = f"Risk too high (${risk_amount:.2f} > ${self.limits.max_risk_per_trade_usd:.2f})"
            logger.warning(msg)
            return (False, msg)

        return (True, f"Risk OK: ${risk_amount:.2f} ({risk_percent:.2f}%)")

    def manage_open_positions(
        self,
        positions: List[Position],
        connector,  # MT5Connector instance
    ) -> Dict[str, int]:
        """
        Manage open positions: trailing stops, exits, etc.

        Args:
            positions: List of open positions
            connector: MT5Connector to execute modifications

        Returns:
            Dict with count of updates (updated_stops, closed_expired)
        """
        result = {"updated_stops": 0, "closed_expired": 0}

        for position in positions:
            # Update trailing stop if enabled
            if self.limits.update_trailing_stops and self.limits.trailing_stop_distance:
                if self._should_update_trailing_stop(position):
                    new_sl = self._calculate_trailing_stop(position)
                    if new_sl and new_sl != position.stop_loss:
                        res = connector.modify_order(position.ticket, new_sl, position.take_profit)
                        if res.get("status") == "modified":
                            result["updated_stops"] += 1
                            logger.info(f"Updated trailing stop for {position.symbol} @ {new_sl}")

            # Close if exceeded time horizon
            if self.limits.close_expired_positions:
                if self._should_close_position(position):
                    res = connector.close_position(position.ticket, position.volume)
                    if res.get("status") == "closed":
                        result["closed_expired"] += 1
                        logger.info(f"Closed expired position {position.symbol} ticket {position.ticket}")

        return result

    def _should_update_trailing_stop(self, position: Position) -> bool:
        """Check if position should have trailing stop updated."""
        # Only update if price has moved favorably
        if position.type.value == "BUY":
            # Buy: update if current price > entry price
            return position.current_price > position.entry_price
        else:
            # Sell: update if current price < entry price
            return position.current_price < position.entry_price

    def _calculate_trailing_stop(self, position: Position) -> Optional[float]:
        """Calculate new trailing stop level."""
        if not self.limits.trailing_stop_distance:
            return None

        # Very simplified: just add/subtract distance from current price
        distance = self.limits.trailing_stop_distance * 0.0001  # Convert pips to price

        if position.type.value == "BUY":
            return position.current_price - distance
        else:
            return position.current_price + distance

    def _should_close_position(self, position: Position) -> bool:
        """Check if position exceeded time horizon."""
        # Would need max_holding_time from the original order
        # For now, just return False (no auto-closing by time)
        return False

    def _is_new_trading_day(self, now: datetime) -> bool:
        """Check if it's a new trading day (for daily loss tracking)."""
        if not self._daily_start_time:
            return False

        # Consider it a new day if 20+ hours passed (accounting for market hours)
        return (now - self._daily_start_time).total_seconds() > 20 * 3600

    def get_risk_metrics(self, account_info: AccountInfo) -> Dict[str, float]:
        """
        Get current risk metrics.

        Args:
            account_info: Current account state

        Returns:
            Dict with risk metrics
        """
        metrics = {
            "balance": account_info.balance,
            "equity": account_info.equity,
            "free_margin": account_info.free_margin,
            "margin_level": account_info.margin_level,
        }

        if self.limits.max_daily_loss and self._daily_start_balance:
            daily_loss = self._daily_start_balance - account_info.balance
            metrics["daily_loss"] = daily_loss
            metrics["daily_loss_remaining"] = self.limits.max_daily_loss - daily_loss

        if self.limits.max_drawdown and self._peak_equity:
            drawdown = self._peak_equity - account_info.equity
            metrics["drawdown"] = drawdown
            metrics["drawdown_remaining"] = self.limits.max_drawdown - drawdown

        return metrics

    def reset_daily_tracking(self):
        """Reset daily loss tracking (e.g., at start of trading day)."""
        self._daily_start_balance = None
        self._daily_start_time = None

    def reset_peak_equity(self, current_equity: float):
        """Reset peak equity for drawdown calculation."""
        self._peak_equity = current_equity
