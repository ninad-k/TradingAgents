"""
Monitoring scheduler: periodically runs analysis for each watchlist symbol.

Runs as a background thread alongside the FastAPI dashboard server.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional, Callable, Dict, Any

from tradingagents.monitor.watchlist import WatchlistEntry, watchlist
from tradingagents.monitor.symbols import is_tradingview_symbol

logger = logging.getLogger(__name__)


class AnalysisResult:
    """Result from a single symbol analysis run."""

    def __init__(self, symbol: str, success: bool, signal: str, decision_text: str, error: Optional[str] = None):
        self.symbol = symbol
        self.success = success
        self.signal = signal              # "BUY" / "HOLD" / "SELL" / "UNKNOWN"
        self.decision_text = decision_text
        self.error = error
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "success": self.success,
            "signal": self.signal,
            "decision_text": self.decision_text,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


def _extract_signal(final_state: Dict) -> str:
    """Extract BUY/HOLD/SELL signal from the final trading state."""
    decision = final_state.get("final_trade_decision", "") or ""
    decision_upper = decision.upper()

    for keyword in ["BUY", "SELL", "HOLD"]:
        if keyword in decision_upper:
            return keyword

    # Check trader plan too
    trader_plan = final_state.get("trader_investment_plan", "") or ""
    for keyword in ["BUY", "SELL", "HOLD"]:
        if keyword in trader_plan.upper():
            return keyword

    return "UNKNOWN"


def _run_single_analysis(entry: WatchlistEntry, config: Dict, event_callback: Optional[Callable] = None) -> AnalysisResult:
    """Run analysis for one watchlist symbol. Returns AnalysisResult."""
    symbol = entry.symbol
    analysis_date = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Starting analysis for {symbol} ({entry.display_name})")

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.dataflows.config import set_config, get_config

        # Configure vendors: use TradingView for forex/commodities
        symbol_config = config.copy()
        if entry.use_tradingview:
            symbol_config["data_vendors"] = {
                "core_stock_apis": "tradingview",
                "technical_indicators": "tradingview",
                # Forex has no fundamentals or insider data
                "fundamental_data": "yfinance",
                "news_data": "yfinance",
            }

        # Build the graph with only applicable analysts
        graph = TradingAgentsGraph(
            selected_analysts=entry.analysts,
            config=symbol_config,
            debug=False,
        )

        final_state, _ = graph.propagate(symbol, analysis_date)

        signal = _extract_signal(final_state)
        decision_text = final_state.get("final_trade_decision", "No decision generated.")

        watchlist.update_result(symbol, decision_text, signal)

        result = AnalysisResult(
            symbol=symbol,
            success=True,
            signal=signal,
            decision_text=decision_text,
        )

        logger.info(f"Analysis complete for {symbol}: {signal}")

        if event_callback:
            event_callback("analysis_complete", result.to_dict())

        return result

    except Exception as e:
        logger.error(f"Analysis failed for {symbol}: {e}", exc_info=True)
        result = AnalysisResult(
            symbol=symbol,
            success=False,
            signal="UNKNOWN",
            decision_text="",
            error=str(e),
        )
        if event_callback:
            event_callback("analysis_error", result.to_dict())
        return result


class MonitorScheduler:
    """Background scheduler that runs watchlist analysis periodically."""

    def __init__(self, check_interval_seconds: int = 60):
        """
        Args:
            check_interval_seconds: How often to check whether any symbol is due for analysis.
        """
        self.check_interval = check_interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._event_callback: Optional[Callable] = None
        self._results: Dict[str, AnalysisResult] = {}
        self._config: Dict = {}

    def set_config(self, config: Dict):
        """Set the LLM/app config to use for analysis runs."""
        self._config = config

    def set_event_callback(self, callback: Callable):
        """Register a callback that fires when an analysis completes."""
        self._event_callback = callback

    def start(self):
        """Start the background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="MonitorScheduler")
        self._thread.start()
        logger.info(f"MonitorScheduler started (check interval: {self.check_interval}s)")

    def stop(self):
        """Stop the background monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("MonitorScheduler stopped")

    def get_result(self, symbol: str) -> Optional[AnalysisResult]:
        """Get the latest analysis result for a symbol."""
        return self._results.get(symbol.upper())

    def get_all_results(self) -> Dict[str, Dict]:
        """Get all latest results as dicts."""
        return {sym: r.to_dict() for sym, r in self._results.items()}

    def trigger_now(self, symbol: str) -> Optional[AnalysisResult]:
        """Immediately run analysis for a specific symbol (blocking)."""
        entry = watchlist.get(symbol)
        if not entry:
            logger.warning(f"Symbol {symbol} not in watchlist")
            return None
        result = _run_single_analysis(entry, self._config, self._event_callback)
        self._results[symbol.upper()] = result
        return result

    def _loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                due = watchlist.due_for_analysis()
                for entry in due:
                    if not self._running:
                        break
                    result = _run_single_analysis(entry, self._config, self._event_callback)
                    self._results[entry.symbol] = result
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}", exc_info=True)

            # Wait before next check cycle
            for _ in range(self.check_interval):
                if not self._running:
                    return
                time.sleep(1)


# Global singleton scheduler
scheduler = MonitorScheduler(check_interval_seconds=60)
