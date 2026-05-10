"""
CLI interface for order approval.

Displays pending orders and allows user to approve, reject, or defer them.
"""

from typing import Optional
from tradingagents.brokers.execution_engine import ExecutionEngine
from tradingagents.brokers.models import PendingOrder

try:
    import questionary
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False


def display_pending_order(pending: PendingOrder) -> None:
    """Display a pending order in formatted table."""

    print("\n" + "="*80)
    print(" MT5 ORDER APPROVAL")
    print("="*80)

    print(f"\n📊 TRADING DECISION")
    print(f"  Pending ID:  {pending.pending_id}")
    print(f"  Decision:    {pending.order.decision_id}")

    print(f"\n💱 ORDER DETAILS")
    print(f"  Symbol:      {pending.order.symbol}")
    print(f"  Action:      {pending.order.action.value}")
    print(f"  Volume:      {pending.order.volume} lots")

    print(f"\n📈 PRICE LEVELS")
    print(f"  Entry Price: {pending.order.entry_price}")
    print(f"  Stop Loss:   {pending.order.stop_loss}")
    print(f"  Take Profit: {pending.order.take_profit}")

    print(f"\n⚠️ RISK ANALYSIS")
    print(f"  Risk/Trade:  ${pending.risk_per_trade:.2f}")
    if pending.reward_target:
        print(f"  Reward Tgt:  ${pending.reward_target:.2f}")
    if pending.risk_reward_ratio:
        print(f"  Risk/Reward: 1:{pending.risk_reward_ratio:.2f}")

    print(f"\n💼 ACCOUNT STATUS")
    print(f"  Balance:     ${pending.account_info.balance:.2f}")
    print(f"  Equity:      ${pending.account_info.equity:.2f}")
    print(f"  Margin:      {pending.account_info.margin_level:.1f}%")

    print(f"\n📋 REASONING")
    print(f"  {pending.decision_reasoning[:200]}...")

    if pending.risk_check_message:
        print(f"\n✓ RISK CHECK")
        print(f"  {pending.risk_check_message}")

    print("\n" + "="*80)


def approve_pending_order_cli(engine: ExecutionEngine) -> Optional[str]:
    """
    Interactive CLI for approving pending orders.

    Args:
        engine: ExecutionEngine instance with pending orders

    Returns:
        ID of executed order, or None if no action taken
    """

    pending_orders = engine.get_pending_orders()

    if not pending_orders:
        print("\n✓ No pending orders to review.")
        return None

    # Display all pending orders
    for i, pending in enumerate(pending_orders, 1):
        print(f"\n[Order {i}/{len(pending_orders)}]")
        display_pending_order(pending)

        if HAS_QUESTIONARY:
            # Interactive approval with questionary
            action = questionary.select(
                "Action:",
                choices=["Approve & Execute", "Reject", "Defer", "View Details"],
                use_shortcuts=True,
            ).ask()

            if action == "Approve & Execute":
                result = engine.approve_order(pending.pending_id)
                if result:
                    print(f"\n✅ Order executed! Ticket: {result.ticket}")
                    return pending.pending_id
                else:
                    print("\n❌ Execution failed. See logs for details.")

            elif action == "Reject":
                reason = questionary.text("Rejection reason:").ask()
                engine.reject_order(pending.pending_id, reason)
                print(f"\n✓ Order rejected.")

            elif action == "Defer":
                print(f"\n⏸ Order deferred. Review later.")

            elif action == "View Details":
                data = engine.get_approval_ui_data(pending.pending_id)
                if data:
                    print("\n" + str(data))

        else:
            # Fallback without questionary: simple input
            print("\nOptions: (A)pprove  (R)eject  (D)efer  (Q)uit")
            choice = input("Action [A/R/D/Q]: ").upper().strip()

            if choice == "A":
                result = engine.approve_order(pending.pending_id)
                if result:
                    print(f"\n✅ Order executed! Ticket: {result.ticket}")
                    return pending.pending_id

            elif choice == "R":
                reason = input("Rejection reason: ") or "User rejected"
                engine.reject_order(pending.pending_id, reason)
                print(f"\n✓ Order rejected.")

            elif choice == "D":
                print(f"\n⏸ Order deferred.")

            elif choice == "Q":
                break

    return None


def show_execution_summary(engine: ExecutionEngine) -> None:
    """Display execution summary."""

    summary = engine.get_execution_summary()

    print("\n" + "="*80)
    print(" EXECUTION SUMMARY")
    print("="*80)

    print(f"\nPending Orders:    {summary['total_pending']}")
    print(f"Executed:          {summary['total_executed']}")
    print(f"Failed:            {summary['total_failed']}")
    print(f"Total at Risk:     ${summary['total_at_risk']:.2f}")

    if summary['pending_ids']:
        print(f"\nPending Order IDs:")
        for pending_id in summary['pending_ids']:
            print(f"  - {pending_id}")

    print("\n" + "="*80)
