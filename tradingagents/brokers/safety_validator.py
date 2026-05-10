"""
Safety validator for MT5 execution.

Comprehensive safety checks before execution and monitoring during trading.
"""

import logging
from typing import List, Tuple
from datetime import datetime, timedelta

from tradingagents.brokers.models import MT5Order, AccountInfo, RiskLimits

logger = logging.getLogger(__name__)


class SafetyValidator:
    """Validate safety requirements before and during trading."""

    # Safety thresholds
    MIN_ACCOUNT_BALANCE = 100.0  # USD
    MIN_MARGIN_LEVEL = 100.0  # %
    MAX_ORDERS_PER_HOUR = 10
    MAX_FAILED_ORDERS_PERCENT = 50  # % of orders that can fail

    @staticmethod
    def validate_pre_execution(
        order: MT5Order,
        account_info: AccountInfo,
        risk_limits: RiskLimits,
    ) -> Tuple[bool, List[str]]:
        """
        Validate order before execution.

        Args:
            order: Order to validate
            account_info: Current account state
            risk_limits: Risk limits configuration

        Returns:
            (is_valid, list of warnings/errors)
        """

        issues = []

        # 1. Account balance check
        if account_info.balance < SafetyValidator.MIN_ACCOUNT_BALANCE:
            issues.append(f"Account balance too low: ${account_info.balance}")

        # 2. Margin level check
        if account_info.margin_level < SafetyValidator.MIN_MARGIN_LEVEL:
            issues.append(f"Margin level critical: {account_info.margin_level}%")

        # 3. Free margin check
        estimated_margin_needed = order.volume * 1000  # Rough estimate
        if estimated_margin_needed > account_info.free_margin:
            issues.append(f"Insufficient margin: need ${estimated_margin_needed}, have ${account_info.free_margin}")

        # 4. Risk per trade check
        if order.max_loss_per_trade:
            max_risk_percent = (order.max_loss_per_trade / account_info.equity) * 100
            if max_risk_percent > 5.0:  # Hard limit: 5% per trade
                issues.append(f"Risk per trade too high: {max_risk_percent:.2f}%")

        # 5. Stop loss validation
        if not order.stop_loss:
            issues.append("WARNING: No stop loss set")

        # 6. Position size validation
        if order.volume <= 0:
            issues.append("Invalid position size: <= 0")

        if order.volume > risk_limits.max_position_size or risk_limits.max_position_size:
            issues.append(f"Position size exceeds limit: {order.volume}")

        # 7. Symbol validation
        if not order.symbol or len(order.symbol) < 2:
            issues.append(f"Invalid symbol: {order.symbol}")

        return len(issues) == 0, issues

    @staticmethod
    def validate_account_health(account_info: AccountInfo) -> Tuple[bool, str]:
        """
        Validate overall account health.

        Args:
            account_info: Account information

        Returns:
            (is_healthy, status_message)
        """

        if account_info.margin_level < 50:
            return False, "CRITICAL: Margin call risk"

        if account_info.margin_level < 100:
            return False, "WARNING: Low margin level"

        if account_info.balance <= 0:
            return False, "ERROR: Account balance is zero or negative"

        if account_info.equity < account_info.balance * 0.8:
            return False, "WARNING: Significant unrealized loss"

        return True, "Account healthy"

    @staticmethod
    def get_risk_profile(
        account_info: AccountInfo,
        risk_limits: RiskLimits,
    ) -> dict:
        """
        Get current risk profile and metrics.

        Args:
            account_info: Account information
            risk_limits: Risk limits

        Returns:
            Dict with risk metrics
        """

        return {
            "account_balance": account_info.balance,
            "equity": account_info.equity,
            "margin_level": account_info.margin_level,
            "free_margin": account_info.free_margin,
            "unrealized_pl": account_info.equity - account_info.balance,
            "pl_percent": ((account_info.equity - account_info.balance) / account_info.balance * 100)
                if account_info.balance else 0,
            "max_daily_loss": risk_limits.max_daily_loss,
            "max_drawdown": risk_limits.max_drawdown,
            "max_positions": risk_limits.max_open_positions,
            "health_status": "GOOD" if account_info.margin_level > 200 else "WARNING" if account_info.margin_level > 100 else "CRITICAL",
        }


class ExecutionSafetyChecklist:
    """Safety checklist for execution setup."""

    @staticmethod
    def run_safety_checklist() -> dict:
        """Run comprehensive safety checklist."""

        checklist = {
            "connectivity": {"status": "UNCHECKED", "notes": ""},
            "account": {"status": "UNCHECKED", "notes": ""},
            "risk_limits": {"status": "UNCHECKED", "notes": ""},
            "approval_mode": {"status": "UNCHECKED", "notes": ""},
            "monitoring": {"status": "UNCHECKED", "notes": ""},
            "backups": {"status": "UNCHECKED", "notes": ""},
        }

        print("\n" + "="*80)
        print(" MT5 EXECUTION SAFETY CHECKLIST")
        print("="*80)

        # 1. Connectivity
        print("\n✓ 1. CONNECTIVITY")
        print("   [ ] MT5 connection established")
        print("   [ ] Account credentials verified")
        print("   [ ] Demo account tested (before live)")
        checklist["connectivity"]["status"] = "REVIEW"

        # 2. Account
        print("\n✓ 2. ACCOUNT")
        print("   [ ] Minimum balance requirement met ($100+)")
        print("   [ ] Margin level adequate (>100%)")
        print("   [ ] Free margin sufficient for test trade")
        checklist["account"]["status"] = "REVIEW"

        # 3. Risk Limits
        print("\n✓ 3. RISK LIMITS")
        print("   [ ] Daily loss limit set ($X)")
        print("   [ ] Max drawdown limit set ($X)")
        print("   [ ] Max positions set (default: 5)")
        print("   [ ] Risk per trade set (default: 2%)")
        checklist["risk_limits"]["status"] = "REVIEW"

        # 4. Approval Mode
        print("\n✓ 4. APPROVAL MODE")
        print("   [ ] Semi-auto mode enabled (NOT auto-approve)")
        print("   [ ] Approval interface tested")
        print("   [ ] User can review before execution")
        checklist["approval_mode"]["status"] = "REVIEW"

        # 5. Monitoring
        print("\n✓ 5. MONITORING")
        print("   [ ] Execution logs enabled")
        print("   [ ] Decision tracking enabled")
        print("   [ ] Alerts configured")
        print("   [ ] Monitoring dashboard accessible")
        checklist["monitoring"]["status"] = "REVIEW"

        # 6. Backups
        print("\n✓ 6. BACKUPS & RECOVERY")
        print("   [ ] Database backups configured")
        print("   [ ] Execution logs backed up")
        print("   [ ] Recovery procedures documented")
        checklist["backups"]["status"] = "REVIEW"

        print("\n" + "="*80)
        return checklist

    @staticmethod
    def print_safety_guide() -> None:
        """Print safety operations guide."""

        print("\n" + "="*80)
        print(" MT5 EXECUTION SAFETY GUIDE")
        print("="*80)

        print("\n📋 PRE-EXECUTION")
        print("   1. Verify MT5 connection")
        print("   2. Check account balance and margin")
        print("   3. Review pending orders")
        print("   4. Confirm all risk limits are set")
        print("   5. Ensure approval mode is enabled")

        print("\n⚙️ DURING EXECUTION")
        print("   1. Monitor open positions real-time")
        print("   2. Watch margin level closely")
        print("   3. Review execution logs")
        print("   4. Be ready to close positions manually if needed")
        print("   5. Do NOT ignore warning alerts")

        print("\n🛑 EMERGENCY PROCEDURES")
        print("   1. Close MT5 connection immediately if:")
        print("      - Margin level drops below 100%")
        print("      - Daily loss limit exceeded")
        print("      - Suspicious order activity")
        print("      - System malfunction")
        print("   2. Manual order closing:")
        print("      - Login to MT5 terminal directly")
        print("      - Close all positions manually")
        print("      - Review trading history")
        print("   3. After incident:")
        print("      - Document what happened")
        print("      - Review execution logs")
        print("      - Investigate root cause")
        print("      - Update procedures if needed")

        print("\n✅ BEST PRACTICES")
        print("   ✓ Always use demo account first")
        print("   ✓ Start with small position sizes")
        print("   ✓ Review every pending order before approval")
        print("   ✓ Monitor the first hour of trading closely")
        print("   ✓ Use trailing stops to protect profits")
        print("   ✓ Set time-based exits to avoid overnight risk")
        print("   ✓ Keep execution logs and decision records")
        print("   ✓ Regular audits of execution performance")

        print("\n❌ WHAT TO AVOID")
        print("   ✗ Do NOT enable auto-approval (always review)")
        print("   ✗ Do NOT trade without stop losses")
        print("   ✗ Do NOT risk more than 2% per trade")
        print("   ✗ Do NOT over-leverage (high position sizes)")
        print("   ✗ Do NOT ignore warning messages")
        print("   ✗ Do NOT leave system unmonitored while trading")
        print("   ✗ Do NOT skip demo account testing")

        print("\n" + "="*80)
