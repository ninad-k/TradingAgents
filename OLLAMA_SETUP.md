# Owen + TradingAgents Ollama Setup Guide

## Quick Start

### 1. Pull the Owen Model (if not already installed)

```bash
ollama pull owen
```

Or if you have a different model variant:
```bash
ollama pull owen:latest
ollama pull owen:small      # if available for smaller size
```

To check available models:
```bash
ollama list
```

### 2. Verify Ollama is Running

```bash
curl http://localhost:11434/api/tags
```

Should return JSON with your models listed.

### 3. Use Owen with TradingAgents

#### Option A: Interactive CLI (Recommended for Testing)

```bash
tradingagents
# or from source:
python -m cli.main
```

When prompted:
- **LLM Provider:** Select `Ollama`
- **Shallow thinking model:** Enter `owen:latest`
- **Deep thinking model:** Enter `owen:latest`
- **Ticker:** Your desired stock (e.g., NVDA)
- **Date:** Analysis date (e.g., 2026-01-15)

#### Option B: Python Script (for Integration)

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Configure with Owen
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "owen:latest"
config["quick_think_llm"] = "owen:latest"

# Create and run the trading agent
ta = TradingAgentsGraph(debug=True, config=config)
ticker = "NVDA"
date = "2026-01-15"
_, decision = ta.propagate(ticker, date)

print(f"\n{ticker} Decision: {decision}")
```

#### Option C: Run the Helper Script

```bash
python run_with_owen.py
```

This will run a full analysis with Owen as the default model.

## Using Different Owen Variants (if available)

For faster quick decisions with smaller models:
```python
config["quick_think_llm"] = "owen:small"      # Quick, lightweight reasoning
config["deep_think_llm"] = "owen:latest"      # Full quality reasoning
```

## Troubleshooting

**Error: Connection refused**
- Make sure Ollama is running: `ollama serve`
- Check it's on port 11434: `curl http://localhost:11434/api/tags`

**Error: model not found**
- Pull the model first: `ollama pull owen`
- Verify it's installed: `ollama list`

**Slow responses**
- Owen may be a large model. Check available RAM.
- Try using a smaller variant if available (e.g., `owen:small`)
- Monitor CPU/GPU usage while running

## Model Selection Tips

- **For testing:** Use smaller models like `gemma4:e4b` first to verify setup
- **For production:** Use `owen:latest` for best quality
- **For development:** Use different models for `quick_think_llm` vs `deep_think_llm`:
  ```python
  config["quick_think_llm"] = "gemma4:e4b"       # Fast
  config["deep_think_llm"] = "owen:latest"       # Better quality
  ```

## Available Local Models

Check what's installed:
```bash
ollama list
```

Current available models in this setup:
- `qwen3.6:latest` (23 GB)
- `gemma4:e4b` (9.6 GB)
- (Pull Owen when ready: `ollama pull owen`)

## Next Steps

1. Pull Owen: `ollama pull owen`
2. Try CLI: `tradingagents`
3. Try script: `python run_with_owen.py`
4. Customize in your own code with the config pattern shown above
