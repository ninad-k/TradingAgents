"""
Analytics and monitoring for MT5 execution.

Tracks decision outcomes, execution metrics, and performance analytics.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from tradingagents.brokers.models import ExecutionLog, OrderStatus

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

logger = logging.getLogger(__name__)


class ExecutionAnalytics:
    """Analyze execution performance and metrics."""

    def __init__(self):
        """Initialize analytics."""
        self.executions: List[ExecutionLog] = []
        self.performance_cache = None
        self.cache_time = None

    def add_execution(self, log_entry: ExecutionLog) -> None:
        """Add execution log entry."""
        self.executions.append(log_entry)
        self.performance_cache = None  # Invalidate cache

    def get_performance_metrics(self, time_period: str = "all") -> Dict:
        """
        Get performance metrics for a time period.

        Args:
            time_period: "all", "day", "week", "month"

        Returns:
            Dict with performance metrics
        """

        if self.performance_cache and time_period == "all":
            return self.performance_cache

        # Filter by time period
        cutoff_time = self._get_cutoff_time(time_period)
        filtered = [e for e in self.executions if e.timestamp > cutoff_time]

        if not filtered:
            return self._empty_metrics()

        # Calculate metrics
        metrics = {
            "total_actions": len(filtered),
            "executions": sum(1 for e in filtered if e.action == "executed"),
            "proposals": sum(1 for e in filtered if e.action == "proposed"),
            "approvals": sum(1 for e in filtered if e.action == "approved"),
            "rejections": sum(1 for e in filtered if e.action == "rejected"),
            "failures": sum(1 for e in filtered if e.action == "failed"),
            "approval_rate": self._calculate_approval_rate(filtered),
            "by_symbol": self._group_by_symbol(filtered),
            "by_action": self._group_by_action(filtered),
            "time_period": time_period,
            "start_time": cutoff_time.isoformat(),
            "end_time": datetime.utcnow().isoformat(),
        }

        if time_period == "all":
            self.performance_cache = metrics
            self.cache_time = datetime.utcnow()

        return metrics

    def get_decision_outcomes(self) -> Dict:
        """Get outcomes of trading decisions."""

        outcomes = {
            "total_decisions": 0,
            "approved": 0,
            "rejected": 0,
            "executed": 0,
            "failed": 0,
            "pending": 0,
            "by_symbol": defaultdict(lambda: {"approved": 0, "rejected": 0, "executed": 0}),
        }

        for log_entry in self.executions:
            if log_entry.action == "proposed":
                outcomes["total_decisions"] += 1

            if log_entry.action == "approved":
                outcomes["approved"] += 1
            elif log_entry.action == "rejected":
                outcomes["rejected"] += 1
            elif log_entry.action == "executed":
                outcomes["executed"] += 1
            elif log_entry.action == "failed":
                outcomes["failed"] += 1

            # By symbol
            symbol = log_entry.symbol
            if log_entry.action == "approved":
                outcomes["by_symbol"][symbol]["approved"] += 1
            elif log_entry.action == "rejected":
                outcomes["by_symbol"][symbol]["rejected"] += 1
            elif log_entry.action == "executed":
                outcomes["by_symbol"][symbol]["executed"] += 1

        return dict(outcomes)

    def get_symbol_statistics(self, symbol: str) -> Dict:
        """Get statistics for a specific symbol."""

        symbol_logs = [e for e in self.executions if e.symbol == symbol]

        if not symbol_logs:
            return {"symbol": symbol, "no_data": True}

        return {
            "symbol": symbol,
            "total_actions": len(symbol_logs),
            "executions": sum(1 for e in symbol_logs if e.action == "executed"),
            "rejections": sum(1 for e in symbol_logs if e.action == "rejected"),
            "success_rate": self._calculate_success_rate(symbol_logs),
            "first_action": symbol_logs[0].timestamp.isoformat(),
            "last_action": symbol_logs[-1].timestamp.isoformat(),
            "action_history": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "action": e.action,
                    "details": e.details,
                }
                for e in symbol_logs[-10:]  # Last 10 actions
            ]
        }

    def print_analytics_report(self) -> None:
        """Print comprehensive analytics report."""

        metrics = self.get_performance_metrics()
        outcomes = self.get_decision_outcomes()

        print("\n" + "="*80)
        print(" EXECUTION ANALYTICS REPORT")
        print("="*80)

        print(f"\n📊 OVERALL METRICS")
        print(f"  Total Actions:    {metrics['total_actions']}")
        print(f"  Executions:       {metrics['executions']}")
        print(f"  Proposals:        {metrics['proposals']}")
        print(f"  Approvals:        {metrics['approvals']}")
        print(f"  Rejections:       {metrics['rejections']}")
        print(f"  Failures:         {metrics['failures']}")
        print(f"  Approval Rate:    {metrics['approval_rate']:.1f}%")

        print(f"\n📈 DECISION OUTCOMES")
        print(f"  Total Decisions:  {outcomes['total_decisions']}")
        print(f"  Approved:         {outcomes['approved']}")
        print(f"  Rejected:         {outcomes['rejected']}")
        print(f"  Executed:         {outcomes['executed']}")
        print(f"  Failed:           {outcomes['failed']}")

        if metrics['by_symbol']:
            print(f"\n💱 BY SYMBOL")
            for symbol, count in sorted(metrics['by_symbol'].items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {symbol:8s} : {count} actions")

        print(f"\n📅 PERIOD: {metrics['time_period']}")
        print(f"  From: {metrics['start_time']}")
        print(f"  To:   {metrics['end_time']}")

        print("\n" + "="*80)

    def export_to_csv(self, filename: str) -> None:
        """Export execution history to CSV."""
        import csv

        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=['timestamp', 'decision_id', 'action', 'symbol', 'ticket', 'details']
                )

                writer.writeheader()
                for log in self.executions:
                    writer.writerow({
                        'timestamp': log.timestamp.isoformat(),
                        'decision_id': log.decision_id,
                        'action': log.action,
                        'symbol': log.symbol,
                        'ticket': log.ticket,
                        'details': str(log.details),
                    })

            logger.info(f"Analytics exported to {filename}")
        except Exception as e:
            logger.error(f"Error exporting analytics: {e}")

    # Private methods

    def _get_cutoff_time(self, period: str) -> datetime:
        """Get cutoff time for period filtering."""
        now = datetime.utcnow()

        if period == "day":
            return now - timedelta(days=1)
        elif period == "week":
            return now - timedelta(weeks=1)
        elif period == "month":
            return now - timedelta(days=30)
        else:  # "all"
            return datetime.min

    def _calculate_approval_rate(self, logs: List[ExecutionLog]) -> float:
        """Calculate approval rate percentage."""
        proposals = sum(1 for e in logs if e.action == "proposed")
        approvals = sum(1 for e in logs if e.action == "approved")

        if proposals == 0:
            return 0.0

        return (approvals / proposals) * 100

    def _calculate_success_rate(self, logs: List[ExecutionLog]) -> float:
        """Calculate success rate (executed / total)."""
        executions = sum(1 for e in logs if e.action == "executed")
        total = len(logs)

        if total == 0:
            return 0.0

        return (executions / total) * 100

    def _group_by_symbol(self, logs: List[ExecutionLog]) -> Dict:
        """Group logs by symbol."""
        grouped = defaultdict(int)

        for log in logs:
            grouped[log.symbol] += 1

        return dict(grouped)

    def _group_by_action(self, logs: List[ExecutionLog]) -> Dict:
        """Group logs by action."""
        grouped = defaultdict(int)

        for log in logs:
            grouped[log.action] += 1

        return dict(grouped)

    def _empty_metrics(self) -> Dict:
        """Return empty metrics template."""
        return {
            "total_actions": 0,
            "executions": 0,
            "proposals": 0,
            "approvals": 0,
            "rejections": 0,
            "failures": 0,
            "approval_rate": 0,
            "by_symbol": {},
            "by_action": {},
        }


class PerformanceDashboard:
    """Real-time performance dashboard."""

    def __init__(self, analytics: ExecutionAnalytics):
        """Initialize dashboard."""
        self.analytics = analytics
        self.console = Console() if RICH_AVAILABLE else None
        self._last_printed_count = 0

    def print_dashboard(self) -> None:
        """Print real-time dashboard."""

        metrics = self.analytics.get_performance_metrics()
        outcomes = self.analytics.get_decision_outcomes()

        if RICH_AVAILABLE:
            self._print_rich_dashboard(metrics, outcomes)
        else:
            self._print_text_dashboard(metrics, outcomes)

    def _print_rich_dashboard(self, metrics: Dict, outcomes: Dict) -> None:
        """Print enhanced dashboard using Rich library."""

        # Create metrics table
        metrics_table = Table(title="Key Metrics", box=box.ROUNDED)
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Value", style="magenta")

        metrics_table.add_row("Total Actions", str(metrics['total_actions']))
        metrics_table.add_row("Executions", str(metrics['executions']))
        metrics_table.add_row("Approvals", str(metrics['approvals']))
        metrics_table.add_row("Rejections", str(metrics['rejections']))
        metrics_table.add_row("Approval Rate", f"{metrics['approval_rate']:.1f}%")
        metrics_table.add_row("Failures", str(metrics['failures']))

        self.console.print(metrics_table)

        # Create decisions table
        decisions_table = Table(title="Decision Outcomes", box=box.ROUNDED)
        decisions_table.add_column("Status", style="cyan")
        decisions_table.add_column("Count", style="magenta")

        decisions_table.add_row("Total Decisions", str(outcomes['total_decisions']))
        decisions_table.add_row("[green]Approved[/green]", str(outcomes['approved']))
        decisions_table.add_row("[red]Rejected[/red]", str(outcomes['rejected']))
        decisions_table.add_row("[blue]Executed[/blue]", str(outcomes['executed']))
        decisions_table.add_row("[yellow]Failed[/yellow]", str(outcomes['failed']))

        self.console.print(decisions_table)

        # Symbol breakdown
        if metrics['by_symbol']:
            symbols_table = Table(title="Top Symbols", box=box.ROUNDED)
            symbols_table.add_column("Symbol", style="cyan")
            symbols_table.add_column("Actions", style="magenta")

            for symbol, count in sorted(metrics['by_symbol'].items(), key=lambda x: x[1], reverse=True)[:5]:
                symbols_table.add_row(symbol, str(count))

            self.console.print(symbols_table)

        # Recent activity
        if self.analytics.executions:
            recent_table = Table(title="Recent Activity (Last 5)", box=box.ROUNDED)
            recent_table.add_column("Time", style="cyan")
            recent_table.add_column("Symbol", style="yellow")
            recent_table.add_column("Action", style="magenta")
            recent_table.add_column("Details", style="white")

            for log in self.analytics.executions[-5:]:
                time_str = log.timestamp.strftime("%H:%M:%S")
                action_color = "green" if log.action == "executed" else "red" if log.action == "rejected" else "yellow"
                action_styled = f"[{action_color}]{log.action}[/{action_color}]"
                details = str(log.details)[:40] if log.details else ""
                recent_table.add_row(time_str, log.symbol, action_styled, details)

            self.console.print(recent_table)

    def _print_text_dashboard(self, metrics: Dict, outcomes: Dict) -> None:
        """Print basic text dashboard (fallback when Rich unavailable)."""

        print("\n" + "╔" + "═"*78 + "╗")
        print("║" + " "*20 + "MT5 EXECUTION REAL-TIME DASHBOARD" + " "*26 + "║")
        print("╚" + "═"*78 + "╝")

        # Row 1: Key metrics
        print(f"\n┌─ KEY METRICS ──────────────────────────────────────────────────────────────┐")
        print(f"│ Total Executions: {metrics['executions']:3d}  │  Success Rate: {metrics['approval_rate']:5.1f}%  │  Failures: {metrics['failures']:3d}  │")
        print(f"└────────────────────────────────────────────────────────────────────────────┘")

        # Row 2: Decision breakdown
        print(f"\n┌─ DECISIONS ────────────────────────────────────────────────────────────────┐")
        print(f"│ Proposed: {outcomes['total_decisions']:3d}  │  Approved: {outcomes['approved']:3d}  │  Rejected: {outcomes['rejected']:3d}  │  Pending: {outcomes['pending']:3d}  │")
        print(f"└────────────────────────────────────────────────────────────────────────────┘")

        # Row 3: Top symbols
        if metrics['by_symbol']:
            print(f"\n┌─ TOP SYMBOLS ──────────────────────────────────────────────────────────────┐")
            for symbol, count in sorted(metrics['by_symbol'].items(), key=lambda x: x[1], reverse=True)[:3]:
                print(f"│ {symbol:12s} : {count:3d} actions" + " "*50 + "│")
            print(f"└────────────────────────────────────────────────────────────────────────────┘")

        # Row 4: Recent activity
        if self.analytics.executions:
            print(f"\n┌─ RECENT ACTIVITY ──────────────────────────────────────────────────────────┐")
            for log in self.analytics.executions[-3:]:
                time_str = log.timestamp.strftime("%H:%M:%S")
                print(f"│ [{time_str}] {log.symbol:8s} {log.action:10s} {str(log.details)[:40]:40s} │")
            print(f"└────────────────────────────────────────────────────────────────────────────┘")

        print()
