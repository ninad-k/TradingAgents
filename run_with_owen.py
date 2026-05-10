#!/usr/bin/env python3
"""
Run TradingAgents with Owen (Ollama) as the default LLM provider.

This script automatically configures the trading framework to use your local
Owen model without requiring interactive CLI selection.

Usage:
    python run_with_owen.py              # Uses defaults: NVDA, 2026-01-15
    python run_with_owen.py MSFT 2026-03-10  # Custom ticker and date
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
import sys

def run_analysis_with_owen(ticker="NVDA", date="2026-01-15"):
    """
    Run trading analysis with Owen (Ollama) as the LLM backbone.

    Args:
        ticker: Stock ticker symbol (default: NVDA)
        date: Analysis date in YYYY-MM-DD format (default: 2026-01-15)
    """

    # Configure Owen as the LLM provider
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "ollama"
    config["deep_think_llm"] = "owen:latest"
    config["quick_think_llm"] = "owen:latest"

    # Optional: Use different models for quick vs deep thinking
    # config["quick_think_llm"] = "gemma4:e4b"      # Faster
    # config["deep_think_llm"] = "owen:latest"      # Better quality

    print(f"\n{'='*60}")
    print(f"TradingAgents with Owen (Ollama)")
    print(f"{'='*60}")
    print(f"Ticker:          {ticker}")
    print(f"Date:            {date}")
    print(f"LLM Provider:    {config['llm_provider']}")
    print(f"Quick Think:     {config['quick_think_llm']}")
    print(f"Deep Think:      {config['deep_think_llm']}")
    print(f"Debate Rounds:   {config['max_debate_rounds']}")
    print(f"{'='*60}\n")

    # Create and run the trading agent graph
    try:
        ta = TradingAgentsGraph(debug=True, config=config)

        print(f"Running analysis for {ticker} on {date}...")
        print("(This may take a few minutes depending on Owen's size and your hardware)\n")

        state, decision = ta.propagate(ticker, date)

        print(f"\n{'='*60}")
        print(f"Analysis Complete")
        print(f"{'='*60}")
        print(f"Trading Decision: {decision}")
        print(f"{'='*60}\n")

        return state, decision

    except ConnectionError as e:
        print(f"\n❌ Error: Cannot connect to Ollama")
        print(f"   Make sure Ollama is running: ollama serve")
        print(f"   Connection attempted: http://localhost:11434/v1")
        print(f"   Error details: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}\n")
        raise

if __name__ == "__main__":
    # Parse command line arguments
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    date = sys.argv[2] if len(sys.argv) > 2 else "2026-01-15"

    # Run the analysis
    run_analysis_with_owen(ticker, date)
