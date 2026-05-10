"""
Integration with TradingAgentsGraph for seamless execution.

Adds execution node to the trading graph and methods for end-to-end workflow.
"""

import logging
from typing import Tuple, Optional
from datetime import datetime

from tradingagents.agents.schemas import PortfolioDecision
from tradingagents.brokers.execution_engine import ExecutionEngine
from tradingagents.brokers.models import ExecutionResult, PendingOrder

logger = logging.getLogger(__name__)


class GraphExecutionIntegration:
    """
    Integration layer between TradingAgentsGraph and ExecutionEngine.

    Provides methods to seamlessly add execution to the trading workflow.
    """

    def __init__(self, execution_engine: ExecutionEngine):
        """
        Initialize integration.

        Args:
            execution_engine: ExecutionEngine instance
        """
        self.engine = execution_engine
        self.pending_decisions = {}  # decision_id -> decision

    def execute_decision(
        self,
        decision: PortfolioDecision,
        symbol: str,
        decision_date: str,
        auto_approve: bool = False,
        decision_id: Optional[str] = None,
    ) -> Tuple[Optional[PendingOrder], Optional[ExecutionResult]]:
        """
        Execute TradingAgents decision on MT5.

        Args:
            decision: PortfolioDecision from TradingAgents
            symbol: Symbol to trade
            decision_date: Decision date
            auto_approve: Auto-approve without user review (use with caution!)
            decision_id: Custom decision ID

        Returns:
            (pending_order, execution_result) - one will be None depending on outcome
        """

        # Generate decision ID if not provided
        if decision_id is None:
            decision_id = f"{symbol}:{decision_date}:{datetime.utcnow().timestamp()}"

        # Store decision
        self.pending_decisions[decision_id] = {
            "decision": decision,
            "symbol": symbol,
            "date": decision_date,
            "created_at": datetime.utcnow(),
        }

        # Process decision
        pending = self.engine.process_decision(
            decision=decision,
            symbol=symbol,
            decision_date=decision_date,
            decision_id=decision_id,
        )

        if not pending:
            logger.info(f"No pending order created for {symbol} ({decision.rating.value})")
            return None, None

        # Auto-approve if requested
        if auto_approve:
            logger.warning(f"Auto-approving order {pending.pending_id} (USE WITH CAUTION)")
            result = self.engine.approve_order(pending.pending_id)
            return pending, result

        # Return pending for user approval
        return pending, None

    def add_execution_node_to_graph(self, trading_graph):
        """
        Add execution node to TradingAgentsGraph.

        Args:
            trading_graph: TradingAgentsGraph instance

        This method would be called from TradingAgentsGraph.__init__()
        """

        def execution_node(state):
            """Node that executes final decision."""
            if not state.get("final_trade_decision"):
                return {}

            decision_markdown = state["final_trade_decision"]
            ticker = state["company_of_interest"]

            # In production, would parse decision and execute
            logger.info(f"Execution node: Processing {ticker}")
            return {"execution_result": None}

        # Would be added to LangGraph StateGraph
        return execution_node

    def get_pending_approvals(self) -> dict:
        """Get all pending orders awaiting approval."""
        pending = self.engine.get_pending_orders()
        return {
            "count": len(pending),
            "orders": [
                {
                    "pending_id": p.pending_id,
                    "symbol": p.order.symbol,
                    "action": p.order.action.value,
                    "volume": p.order.volume,
                    "risk": p.risk_per_trade,
                }
                for p in pending
            ]
        }

    def approve_and_track(self, pending_id: str, user_id: str = "user") -> dict:
        """
        Approve order and track execution.

        Args:
            pending_id: Pending order ID
            user_id: User who approved

        Returns:
            Dict with execution result
        """
        result = self.engine.approve_order(pending_id)

        if result:
            logger.info(f"Order executed by {user_id}: ticket {result.ticket}")
            return {
                "status": "executed",
                "ticket": result.ticket,
                "approved_by": user_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        else:
            return {
                "status": "failed",
                "approved_by": user_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

    def get_execution_stats(self) -> dict:
        """Get execution statistics."""
        summary = self.engine.get_execution_summary()
        history = self.engine.get_execution_history()

        total_trades = summary["total_executed"]
        total_risk = summary["total_at_risk"]

        return {
            "pending": summary["total_pending"],
            "executed": total_trades,
            "failed": summary["total_failed"],
            "total_risk_usd": total_risk,
            "history_entries": len(history),
        }


class TradingAgentsGraphWithExecution:
    """
    Extended TradingAgentsGraph with built-in execution support.

    This would be a subclass or mixin for TradingAgentsGraph.
    """

    def __init__(self, execution_engine: ExecutionEngine = None, **kwargs):
        """
        Initialize graph with optional execution.

        Args:
            execution_engine: ExecutionEngine for trade execution
            **kwargs: Other TradingAgentsGraph arguments
        """
        # super().__init__(**kwargs)  # Call parent init

        self.execution_engine = execution_engine
        if execution_engine:
            self.execution_integration = GraphExecutionIntegration(execution_engine)
        else:
            self.execution_integration = None

    def propagate_and_execute(
        self,
        ticker: str,
        date: str,
        auto_approve: bool = False,
    ) -> Tuple[dict, str, Optional[dict]]:
        """
        Run full analysis AND execute on MT5.

        Args:
            ticker: Stock ticker
            date: Analysis date
            auto_approve: Auto-approve orders (careful!)

        Returns:
            (state, decision, execution_result)
        """

        # Run analysis
        # state, decision = self.propagate(ticker, date)  # From parent
        state = {}  # Placeholder
        decision = None  # Placeholder

        if not decision or not self.execution_integration:
            return state, decision or "", None

        # Execute on MT5
        pending, result = self.execution_integration.execute_decision(
            decision=decision,
            symbol=ticker,
            decision_date=date,
            auto_approve=auto_approve,
        )

        execution_data = None
        if result:
            execution_data = {
                "status": "executed",
                "ticket": result.ticket,
                "price": result.execution_price,
            }
        elif pending:
            execution_data = {
                "status": "pending_approval",
                "pending_id": pending.pending_id,
            }

        return state, decision or "", execution_data


# Helper functions for easy integration

def create_execution_integration(
    connector=None,
    risk_manager=None,
    order_generator=None,
) -> GraphExecutionIntegration:
    """
    Factory function to create execution integration.

    Args:
        connector: MT5Connector instance
        risk_manager: RiskManager instance
        order_generator: OrderGenerator instance

    Returns:
        GraphExecutionIntegration instance
    """

    if not connector or not risk_manager or not order_generator:
        logger.warning("Missing required components for execution")
        return None

    engine = ExecutionEngine(connector, risk_manager, order_generator)
    return GraphExecutionIntegration(engine)


def add_execution_to_graph(trading_graph, execution_engine) -> None:
    """
    Add execution capability to an existing TradingAgentsGraph.

    Args:
        trading_graph: TradingAgentsGraph instance
        execution_engine: ExecutionEngine instance
    """

    integration = GraphExecutionIntegration(execution_engine)
    trading_graph.execution_integration = integration
    trading_graph.execute_decision = integration.execute_decision

    logger.info("Execution capability added to TradingAgentsGraph")
