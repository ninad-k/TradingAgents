# Testing Owen Setup with TradingAgents

This guide walks you through verifying your Owen + Ollama setup works correctly.

## Prerequisites

- Ollama running: `ollama serve` (should be running in background)
- Owen model pulled: `ollama pull owen`
- TradingAgents installed: `pip install .` (from repo root)

## Test 1: Verify Ollama Connection

```bash
# Check if Ollama is running and accessible
curl -s http://localhost:11434/api/tags | jq .

# Expected output:
# {
#   "models": [
#     {
#       "name": "owen:latest",
#       ...
#     },
#     ...
#   ]
# }
```

✅ **Success:** Returns JSON with your models list
❌ **Failure:** Connection refused → Run `ollama serve` first

---

## Test 2: Test Owen Model Directly

```bash
# Run Owen directly to verify it responds
ollama run owen "What is a trading strategy?"
```

✅ **Success:** Returns a response from Owen
❌ **Failure:** "Model not found" → Run `ollama pull owen`

---

## Test 3: Python Import Test

```bash
# Test that TradingAgents can be imported
python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('✓ Import successful')"
```

✅ **Success:** Prints "✓ Import successful"
❌ **Failure:** ImportError → Check installation: `pip install .`

---

## Test 4: LLM Client Factory Test

Test that the Ollama provider is correctly configured:

```python
from tradingagents.llm_clients.factory import create_llm_client

# Create an Ollama LLM client
client = create_llm_client(
    provider="ollama",
    model="owen:latest"
)

print(f"✓ Client created: {type(client).__name__}")
print(f"✓ Provider: ollama")
print(f"✓ Model: owen:latest")
print(f"✓ Base URL: {client.base_url}")
```

✅ **Success:** Prints client type and configuration
❌ **Failure:** Connection error → Make sure Ollama is running

---

## Test 5: Quick LLM Call Test

Test that you can actually call Owen through the client:

```python
from tradingagents.llm_clients.factory import create_llm_client

# Create client
client = create_llm_client(
    provider="ollama",
    model="owen:latest"
)

# Get LLM instance
llm = client.get_llm()

# Make a simple call
response = llm.invoke("Say 'Owen is working!' in one sentence.")

print(f"Response: {response.content}")
```

✅ **Success:** Prints a response from Owen
❌ **Failure:** Check error message
   - "Connection refused" → Run `ollama serve`
   - "Model not found" → Run `ollama pull owen`
   - "Timeout" → Owen may be slow, wait and retry

---

## Test 6: Configuration Test

Test the full configuration setup:

```python
from tradingagents.default_config import DEFAULT_CONFIG

# Create Owen config
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "owen:latest"
config["quick_think_llm"] = "owen:latest"

# Verify config
assert config["llm_provider"] == "ollama", "Provider not set correctly"
assert config["deep_think_llm"] == "owen:latest", "Deep model not set"
assert config["quick_think_llm"] == "owen:latest", "Quick model not set"

print("✓ Configuration test passed")
print(f"  - LLM Provider: {config['llm_provider']}")
print(f"  - Deep Thinking: {config['deep_think_llm']}")
print(f"  - Quick Thinking: {config['quick_think_llm']}")
```

✅ **Success:** Prints configuration details
❌ **Failure:** Assertion error → Check config values

---

## Test 7: TradingAgentsGraph Initialization Test

Test that the full graph can be created with Owen:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create config
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "owen:latest"
config["quick_think_llm"] = "owen:latest"

# Initialize graph
try:
    ta = TradingAgentsGraph(debug=True, config=config)
    print("✓ TradingAgentsGraph initialized successfully")
    print(f"  - LLM Provider: ollama")
    print(f"  - Models: owen:latest")
except Exception as e:
    print(f"✗ Failed to initialize: {e}")
```

✅ **Success:** Prints initialization success
❌ **Failure:** Check error message and ensure Ollama is running

---

## Test 8: Full Analysis Test (IMPORTANT: Takes 10-30 minutes)

Run a complete analysis with Owen. This is the final validation:

```bash
python run_with_owen.py NVDA 2026-01-15
```

Or in Python:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "owen:latest"
config["quick_think_llm"] = "owen:latest"

ta = TradingAgentsGraph(debug=True, config=config)

print("Starting full analysis with Owen...")
print("(This takes 10-30 minutes depending on model size)")

_, decision = ta.propagate("NVDA", "2026-01-15")

print(f"\n✓ Analysis complete!")
print(f"Decision: {decision}")
```

✅ **Success:** Completes analysis and prints decision
❌ **Failure:** 
   - "Connection refused" → Start Ollama
   - "OutOfMemory" → Owen is too large for available RAM
   - "Timeout" → Owen is very slow, may need more resources

---

## Test 9: Using the Helper Script

```bash
# Make sure it's executable (one-time)
chmod +x run_with_owen.py

# Run with defaults (NVDA, 2026-01-15)
python run_with_owen.py

# Run with custom ticker and date
python run_with_owen.py MSFT 2026-02-20

# Run with multiple tickers
python run_with_owen.py AAPL 2026-03-01
python run_with_owen.py TSLA 2026-01-20
```

✅ **Success:** Completes analysis for each ticker
❌ **Failure:** Follow error messages and fix issues

---

## Test 10: CLI Interface Test

Test the interactive CLI with Owen selection:

```bash
tradingagents
```

Or from source:
```bash
python -m cli.main
```

When prompted:
1. Select a ticker (e.g., NVDA)
2. Select a date (e.g., 2026-01-15)
3. When asked for LLM Provider → **Select "Ollama"**
4. When asked for shallow model → Type `owen:latest`
5. When asked for deep model → Type `owen:latest`
6. Continue with analysis

✅ **Success:** CLI launches, accepts Ollama provider, completes analysis
❌ **Failure:** 
   - "Ollama not in provider list" → Check llm_clients/model_catalog.py
   - "Connection error" → Verify Ollama is running

---

## Troubleshooting Matrix

| Issue | Cause | Solution |
|-------|-------|----------|
| "Connection refused" | Ollama not running | `ollama serve` |
| "Model not found" | Owen not pulled | `ollama pull owen` |
| "Out of memory" | Insufficient RAM | Use smaller model (gemma4) or close apps |
| "Timeout" | Owen is slow | Wait, first run is slowest |
| "Import error" | TradingAgents not installed | `pip install .` from repo |
| "Invalid provider" | Config error | Check llm_provider = "ollama" |

---

## Quick Test Script

Save this as `test_owen.py` and run with `python test_owen.py`:

```python
#!/usr/bin/env python3
"""Quick test of Owen setup"""

import sys

print("=" * 60)
print("Owen + TradingAgents Setup Test")
print("=" * 60)

# Test 1: Ollama connection
print("\n[1/4] Testing Ollama connection...", end=" ")
try:
    import requests
    r = requests.get("http://localhost:11434/api/tags", timeout=5)
    if r.status_code == 200:
        models = r.json()["models"]
        owen_found = any("owen" in m["name"] for m in models)
        if owen_found:
            print("✓")
        else:
            print("✗ (Owen not found in models)")
    else:
        print("✗")
except Exception as e:
    print(f"✗ ({e})")
    sys.exit(1)

# Test 2: TradingAgents import
print("[2/4] Testing TradingAgents import...", end=" ")
try:
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    print("✓")
except Exception as e:
    print(f"✗ ({e})")
    sys.exit(1)

# Test 3: LLM client creation
print("[3/4] Testing LLM client creation...", end=" ")
try:
    from tradingagents.llm_clients.factory import create_llm_client
    client = create_llm_client("ollama", "owen:latest")
    print("✓")
except Exception as e:
    print(f"✗ ({e})")
    sys.exit(1)

# Test 4: Graph initialization
print("[4/4] Testing graph initialization...", end=" ")
try:
    from tradingagents.default_config import DEFAULT_CONFIG
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "ollama"
    config["deep_think_llm"] = "owen:latest"
    config["quick_think_llm"] = "owen:latest"
    ta = TradingAgentsGraph(debug=False, config=config)
    print("✓")
except Exception as e:
    print(f"✗ ({e})")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ All tests passed! Owen setup is ready.")
print("=" * 60)
print("\nNext steps:")
print("  1. Run: python run_with_owen.py")
print("  2. Or: tradingagents (and select Ollama)")
```

---

## Expected Timings

| Operation | Time |
|-----------|------|
| Ollama API call | < 1 second |
| Model loading (first run) | 30 seconds - 2 minutes |
| Subsequent API calls | 5-30 seconds per agent |
| Full analysis (4 analysts + researchers) | 10-30 minutes |

---

## System Requirements

- **RAM:** 8GB+ (Owen is typically 8-14GB)
- **Disk:** 20GB+ (for Owen model)
- **GPU:** Optional (faster with GPU, works on CPU)
- **OS:** macOS, Linux, Windows

---

## Getting Help

If tests fail:

1. Check Ollama is running: `ollama serve`
2. Check Owen is installed: `ollama list | grep owen`
3. Test Owen directly: `ollama run owen "hello"`
4. Check all dependencies: `pip list | grep -E "(langchain|langgraph|ollama)"`
5. Review detailed logs: Run with `debug=True`

For more info, see: `OLLAMA_SETUP.md`, `OWEN_QUICKSTART.md`
