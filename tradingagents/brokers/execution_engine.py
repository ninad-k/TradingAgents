"""
ExecutionEngine: Main orchestrator for semi-automated order execution.

Workflow:
1. Receive TradingAgents decision
2. Generate MT5 order
3. Check risk limits
4. Create PendingOrder for user approval
5. Wait for user approval
6. Execute approved order
7. Track execution
8. Manage open positions
"""

import logging
import uuid
from typing import Optional, Dict, List
from datetime import datetime

from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.brokers.mt5_connector import MT5Connector
from tradingagents.brokers.order_generator import OrderGenerator
from tradingagents.brokers.risk_manager import RiskManager
from tradingagents.brokers.models import (
    MT5Order, PendingOrder, ExecutionResult, OrderStatus,
    ExecutionLog, SymbolInfo, AccountInfo, Position
)

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Main execution engine for TradingAgents decisions.

    Handles:
    - Converting decisions to orders
    - Checking risk limits
    - Creating pending orders for approval
    - Executing approved orders
    - Managing open positions
    - Tracking execution history
    """

    def __init__(
        self,
        connector: MT5Connector,
        risk_manager: RiskManager,
        order_generator: OrderGenerator,
        approval_mode: str = "semi_auto",
    ):
        """
        Initialize ExecutionEngine.

        Args:
            connector: MT5Connector instance
            risk_manager: RiskManager instance
            order_generator: OrderGenerator instance
            approval_mode: "semi_auto" (require approval) or "signal_only" (propose only)
        """
        self.connector = connector
        self.risk_manager = risk_manager
        self.order_generator = order_generator
        self.approval_mode = approval_mode

        # Tracking
        self.pending_orders: Dict[str, PendingOrder] = {}  # pending_id -> PendingOrder
        self.execution_history: List[ExecutionLog] = []
        self.execution_results: Dict[str, ExecutionResult] = {}  # decision_id -> result

        logger.info(f"ExecutionEngine initialized (mode: {approval_mode})")

    def process_decision(
        self,
        decision: PortfolioDecision,
        symbol: str,
        decision_date: str,
        decision_id: Optional[str] = None,
    ) -> Optional[PendingOrder]:
        """
        Process TradingAgents decision and create pending order.

        Args:
            decision: PortfolioDecision from TradingAgents
            symbol: Trading symbol (e.g., EURUSD, AAPL)
            decision_date: Date of analysis
            decision_id: Unique decision ID (auto-generated if not provided)

        Returns:
            PendingOrder for user review, or None if Hold or error
        """

        if decision_id is None:
            decision_id = f"{symbol}:{decision_date}:{uuid.uuid4().hex[:8]}"

        # Check for Hold decision
        if decision.rating == PortfolioRating.HOLD:
            logger.info(f"{symbol}: Hold decision, no action")
            return None

        # Connect if not already connected
        if not self.connector.is_connected():
            if not self.connector.connect():
                logger.error("Failed to connect to MT5")
                return None

        # Get account and symbol info
        account_info = self.connector.get_account_info()
        symbol_info = self.connector.get_symbol_info(symbol)

        if not account_info or not symbol_info:
            logger.error(f"Failed to get account/symbol info for {symbol}")
            return None

        # Generate order
        order = self.order_generator.decision_to_order(
            decision=decision,
            symbol=symbol,
            symbol_info=symbol_info,
            account_info=account_info,
            decision_id=decision_id,
        )

        if order is None:
            # Hold decision or no trade generated
            return None

        # Check risk limits
        open_positions = self._get_open_positions()
        allowed, risk_message = self.risk_manager.can_open_trade(order, account_info, open_positions)

        if not allowed:
            logger.warning(f"Order rejected by risk manager: {risk_message}")
            return None

        # Create pending order
        pending = self.order_generator.propose_order(
            decision=decision,
            symbol=symbol,
            symbol_info=symbol_info,
            account_info=account_info,
            decision_id=decision_id,
        )

        if pending:
            pending.risk_check_message = risk_message
            self.pending_orders[pending.pending_id] = pending

            # Log proposal
            self._log_execution(
                decision_id=decision_id,
                action="proposed",
                symbol=symbol,
                details={
                    "pending_id": pending.pending_id,
                    "action": pending.order.action.value,
                    "volume": pending.order.volume,
                    "entry": pending.order.entry_price,
                    "sl": pending.order.stop_loss,
                    "tp": pending.order.take_profit,
                    "risk_per_trade": pending.risk_per_trade,
                }
            )

            logger.info(f"Pending order created: {pending.pending_id}")

        return pending

    def approve_order(self, pending_id: str) -> Optional[ExecutionResult]:
        """
        User approves pending order for execution.

        Args:
            pending_id: ID of pending order to approve

        Returns:
            ExecutionResult from placing the order
        """

        pending = self.pending_orders.get(pending_id)
        if not pending:
            logger.error(f"Pending order not found: {pending_id}")
            return None

        # Mark as approved
        pending.approved_at = datetime.utcnow()

        logger.info(f"Order approved: {pending_id}")
        self._log_execution(
            decision_id=pending.order.decision_id,
            action="approved",
            symbol=pending.order.symbol,
        )

        # Execute the order
        return self.execute_order(pending)

    def reject_order(self, pending_id: str, reason: str = "User rejected") -> None:
        """
        User rejects pending order.

        Args:
            pending_id: ID of pending order
            reason: Rejection reason
        """

        pending = self.pending_orders.get(pending_id)
        if pending:
            logger.info(f"Order rejected: {pending_id} - {reason}")
            self._log_execution(
                decision_id=pending.order.decision_id,
                action="rejected",
                symbol=pending.order.symbol,
                details={"reason": reason}
            )
            del self.pending_orders[pending_id]

    def execute_order(self, pending: PendingOrder) -> Optional[ExecutionResult]:
        """
        Execute an approved pending order on MT5.

        Args:
            pending: PendingOrder to execute

        Returns:
            ExecutionResult with execution details
        """

        order = pending.order

        # Ensure connected
        if not self.connector.is_connected():
            if not self.connector.connect():
                logger.error("Failed to connect to MT5 for execution")
                return None

        # Place order on MT5
        placement_result = self.connector.place_order(order)

        # Create execution result
        result = ExecutionResult(
            decision_id=order.decision_id,
            order=order,
            status=OrderStatus.EXECUTING,
            created_at=order.created_at,
            approved_at=pending.approved_at,
        )

        if placement_result.get("status") == "executed":
            result.status = OrderStatus.EXECUTED
            result.ticket = placement_result.get("ticket")
            result.execution_price = placement_result.get("price")
            result.executed_at = datetime.utcnow()

            # Store account state at execution
            acc = self.connector.get_account_info()
            if acc:
                result.account_balance_at_execution = acc.balance
                result.margin_level_at_execution = acc.margin_level

            logger.info(f"Order executed: ticket {result.ticket} for {order.symbol}")
            self._log_execution(
                decision_id=order.decision_id,
                action="executed",
                symbol=order.symbol,
                ticket=result.ticket,
                details={
                    "volume": order.volume,
                    "execution_price": result.execution_price,
                }
            )
        else:
            result.status = OrderStatus.FAILED
            result.message = placement_result.get("message", "Unknown error")
            logger.error(f"Order execution failed: {result.message}")
            self._log_execution(
                decision_id=order.decision_id,
                action="failed",
                symbol=order.symbol,
                details={"error": result.message}
            )

        # Store result
        self.execution_results[order.decision_id] = result

        # Remove from pending
        if pending.pending_id in self.pending_orders:
            del self.pending_orders[pending.pending_id]

        return result

    def manage_positions(self) -> Dict[str, int]:
        """
        Manage all open positions (trailing stops, time-based exits, etc.).

        Returns:
            Dict with management statistics
        """

        if not self.connector.is_connected():
            return {"error": "Not connected"}

        positions = self._get_open_positions()
        if not positions:
            return {"updated_stops": 0, "closed_expired": 0}

        # Let risk manager handle position management
        result = self.risk_manager.manage_open_positions(positions, self.connector)

        logger.info(f"Position management: {result}")
        return result

    def get_pending_orders(self) -> List[PendingOrder]:
        """Get all pending orders awaiting approval."""
        return list(self.pending_orders.values())

    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return self._get_open_positions()

    def get_execution_history(self) -> List[ExecutionLog]:
        """Get execution history."""
        return self.execution_history

    def get_execution_summary(self) -> Dict:
        """Get summary of executions."""
        total_executed = sum(
            1 for r in self.execution_results.values()
            if r.status == OrderStatus.EXECUTED
        )

        total_failed = sum(
            1 for r in self.execution_results.values()
            if r.status == OrderStatus.FAILED
        )

        total_profit = sum(
            r.order.max_loss_per_trade or 0
            for r in self.execution_results.values()
            if r.status == OrderStatus.EXECUTED
        )

        return {
            "total_pending": len(self.pending_orders),
            "total_executed": total_executed,
            "total_failed": total_failed,
            "total_at_risk": total_profit,
            "pending_ids": list(self.pending_orders.keys()),
        }

    def disconnect(self) -> bool:
        """Disconnect from MT5."""
        return self.connector.disconnect()

    # Internal methods

    def _get_open_positions(self) -> List[Position]:
        """Get all open positions from MT5."""
        return self.connector.get_positions()

    def _log_execution(
        self,
        decision_id: str,
        action: str,
        symbol: str,
        ticket: Optional[int] = None,
        details: Optional[Dict] = None,
    ) -> None:
        """Log an execution event."""

        log_entry = ExecutionLog(
            decision_id=decision_id,
            action=action,
            symbol=symbol,
            ticket=ticket,
            details=details or {},
        )

        self.execution_history.append(log_entry)

    def get_approval_ui_data(self, pending_id: str) -> Optional[Dict]:
        """Get data for approval UI display."""

        pending = self.pending_orders.get(pending_id)
        if not pending:
            return None

        return {
            "pending_id": pending_id,
            "symbol": pending.order.symbol,
            "rating": pending.order.reason,
            "action": pending.order.action.value,
            "volume": pending.order.volume,
            "entry_price": pending.order.entry_price,
            "stop_loss": pending.order.stop_loss,
            "take_profit": pending.order.take_profit,
            "risk_per_trade": pending.risk_per_trade,
            "risk_reward_ratio": pending.risk_reward_ratio,
            "account_balance": pending.account_info.balance,
            "account_equity": pending.account_info.equity,
            "margin_level": pending.account_info.margin_level,
            "reasoning": pending.decision_reasoning,
            "risk_check": pending.risk_check_message,
        }
