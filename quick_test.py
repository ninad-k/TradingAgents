#!/usr/bin/env python3
"""
Quick test to verify Qwen3.6 + TradingAgents is working
This runs without full analysis - just tests the connection and setup
"""

import sys
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

print("="*70)
print("Quick Test: Qwen3.6 + TradingAgents Setup")
print("="*70)

# Test 1: Can we create the LLM client?
print("\n[1/3] Testing Qwen3.6 LLM client creation...", end=" ", flush=True)
try:
    client = create_llm_client("ollama", "qwen3.6:latest")
    print("✓")
except Exception as e:
    print(f"✗\n  Error: {e}")
    print("  Make sure Ollama is running: ollama serve")
    sys.exit(1)

# Test 2: Can we get the LLM instance?
print("[2/3] Testing LLM instance retrieval...", end=" ", flush=True)
try:
    llm = client.get_llm()
    print("✓")
except Exception as e:
    print(f"✗\n  Error: {e}")
    sys.exit(1)

# Test 3: Can we initialize TradingAgentsGraph?
print("[3/3] Testing TradingAgentsGraph initialization...", end=" ", flush=True)
try:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "ollama"
    config["deep_think_llm"] = "qwen3.6:latest"
    config["quick_think_llm"] = "qwen3.6:latest"

    ta = TradingAgentsGraph(debug=False, config=config)
    print("✓")
except Exception as e:
    print(f"✗\n  Error: {e}")
    sys.exit(1)

print("\n" + "="*70)
print("✓ All tests passed! Your setup is ready.")
print("="*70)
print("\nNext step: Run a full analysis")
print("\n  Command 1 (Simple):")
print("    python run_trading_analysis.py")
print("\n  Command 2 (Custom ticker & date):")
print("    python run_trading_analysis.py MSFT 2026-02-20")
print("\n  Command 3 (With debate rounds):")
print("    python run_trading_analysis.py AAPL 2026-03-01 2")
print("\n" + "="*70 + "\n")
