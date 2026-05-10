"""
Example: Using Owen (Ollama) with TradingAgents

This example shows how to configure and run TradingAgents using your local Owen model.
Make sure Ollama is running: ollama serve
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Example 1: Basic Owen Configuration (Recommended)
print("=" * 60)
print("Example 1: Basic Owen Configuration")
print("=" * 60)

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "owen:latest"
config["quick_think_llm"] = "owen:latest"

print(f"LLM Provider: {config['llm_provider']}")
print(f"Deep Thinking Model: {config['deep_think_llm']}")
print(f"Quick Thinking Model: {config['quick_think_llm']}")

# ta = TradingAgentsGraph(debug=True, config=config)
# _, decision = ta.propagate("NVDA", "2026-01-15")
# print(f"Decision: {decision}\n")


# Example 2: Mixed Model Configuration
# Use a smaller/faster model for quick decisions, Owen for deep analysis
print("=" * 60)
print("Example 2: Mixed Model Configuration")
print("=" * 60)

config2 = DEFAULT_CONFIG.copy()
config2["llm_provider"] = "ollama"
config2["quick_think_llm"] = "gemma4:e4b"       # Fast, lightweight
config2["deep_think_llm"] = "owen:latest"       # Full quality reasoning

print(f"LLM Provider: {config2['llm_provider']}")
print(f"Quick Thinking Model (Fast): {config2['quick_think_llm']}")
print(f"Deep Thinking Model (Quality): {config2['deep_think_llm']}")

# ta2 = TradingAgentsGraph(debug=True, config=config2)
# _, decision2 = ta2.propagate("MSFT", "2026-02-20")
# print(f"Decision: {decision2}\n")


# Example 3: Owen with Custom Settings
print("=" * 60)
print("Example 3: Owen with Custom Settings")
print("=" * 60)

config3 = DEFAULT_CONFIG.copy()
config3["llm_provider"] = "ollama"
config3["deep_think_llm"] = "owen:latest"
config3["quick_think_llm"] = "owen:latest"
config3["max_debate_rounds"] = 2              # More debate rounds for complex reasoning
config3["output_language"] = "English"        # Output language

print(f"LLM Provider: {config3['llm_provider']}")
print(f"Models: {config3['deep_think_llm']}")
print(f"Debate Rounds: {config3['max_debate_rounds']}")
print(f"Output Language: {config3['output_language']}")

# ta3 = TradingAgentsGraph(debug=True, config=config3)
# _, decision3 = ta3.propagate("TSLA", "2026-03-01")
# print(f"Decision: {decision3}\n")


# Example 4: Owen with Data Vendor Configuration
print("=" * 60)
print("Example 4: Owen with Data Configuration")
print("=" * 60)

config4 = DEFAULT_CONFIG.copy()
config4["llm_provider"] = "ollama"
config4["deep_think_llm"] = "owen:latest"
config4["quick_think_llm"] = "owen:latest"

# Configure data vendors (yfinance is free, alpha_vantage requires API key)
config4["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Stock prices
    "technical_indicators": "yfinance",      # MACD, RSI, etc.
    "fundamental_data": "yfinance",          # P/E, dividend, etc.
    "news_data": "yfinance",                 # Latest news
}

print(f"LLM Provider: {config4['llm_provider']}")
print(f"Data Vendors: {config4['data_vendors']}")

# ta4 = TradingAgentsGraph(debug=True, config=config4)
# _, decision4 = ta4.propagate("AAPL", "2026-01-20")
# print(f"Decision: {decision4}\n")


# Uncomment below to run a real analysis (takes several minutes):
print("\n" + "=" * 60)
print("To run actual analysis, uncomment one of the examples above")
print("Make sure Ollama is running: ollama serve")
print("=" * 60)

# Example: Run analysis
# ta = TradingAgentsGraph(debug=True, config=config)
# print("\nRunning analysis with Owen...")
# _, decision = ta.propagate("NVDA", "2026-01-15")
# print(f"\nFinal Decision: {decision}")
