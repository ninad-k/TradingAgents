#!/usr/bin/env python3
"""
Run TradingAgents with Qwen3.6 (Ollama) - Optimized for Financial Analysis

Qwen3.6 is the best model for trading analysis due to superior reasoning
and financial domain understanding.

Usage:
    python run_trading_analysis.py              # Uses defaults: NVDA, 2026-01-15
    python run_trading_analysis.py MSFT 2026-03-10  # Custom ticker and date
    python run_trading_analysis.py TSLA 2026-02-15 2  # Custom + debate rounds
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
import sys
import time

def run_trading_analysis(ticker="NVDA", date="2026-01-15", debate_rounds=1):
    """
    Run trading analysis with Qwen3.6 (Ollama).

    Args:
        ticker: Stock ticker symbol (default: NVDA)
        date: Analysis date in YYYY-MM-DD format (default: 2026-01-15)
        debate_rounds: Number of debate rounds (default: 1, max: 3)
    """

    # Configure Qwen3.6 as the LLM provider
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "ollama"
    config["deep_think_llm"] = "qwen3.6:latest"
    config["quick_think_llm"] = "qwen3.6:latest"
    config["max_debate_rounds"] = min(debate_rounds, 3)  # Cap at 3

    print(f"\n{'='*70}")
    print(f"TradingAgents with Qwen3.6 (Ollama)")
    print(f"{'='*70}")
    print(f"Ticker:          {ticker}")
    print(f"Date:            {date}")
    print(f"LLM Provider:    {config['llm_provider']}")
    print(f"Model:           {config['deep_think_llm']}")
    print(f"Debate Rounds:   {config['max_debate_rounds']}")
    print(f"{'='*70}\n")

    # Create and run the trading agent graph
    try:
        print("Initializing TradingAgents with Qwen3.6...")
        ta = TradingAgentsGraph(debug=True, config=config)

        print(f"\n▶ Running financial analysis for {ticker} on {date}...")
        print("  (First run loads the model into memory, subsequent runs are faster)\n")

        start_time = time.time()
        state, decision = ta.propagate(ticker, date)
        elapsed_time = time.time() - start_time

        print(f"\n{'='*70}")
        print(f"✓ Analysis Complete")
        print(f"{'='*70}")
        print(f"Ticker:          {ticker}")
        print(f"Date:            {date}")
        print(f"Time Elapsed:    {elapsed_time:.1f} seconds")
        print(f"Trading Decision: {decision}")
        print(f"{'='*70}\n")

        return state, decision

    except ConnectionError as e:
        print(f"\n❌ Error: Cannot connect to Ollama")
        print(f"   Make sure Ollama is running:")
        print(f"   $ ollama serve")
        print(f"\n   Connection attempted: http://localhost:11434/v1")
        print(f"   Error details: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}\n")
        raise

if __name__ == "__main__":
    # Parse command line arguments
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    date = sys.argv[2] if len(sys.argv) > 2 else "2026-01-15"
    debate_rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    # Run the analysis
    run_trading_analysis(ticker, date, debate_rounds)
