# Owen + TradingAgents Quick Start

## ✅ Your Setup

**Ollama Status:** ✓ Running on http://localhost:11434
**Available Models:**
- qwen3.6:latest (23 GB)
- gemma4:e4b (9.6 GB)

## 📦 Step 1: Pull Owen Model

```bash
ollama pull owen
```

Wait for download to complete. This may take 5-30 minutes depending on model size.

Verify it's installed:
```bash
ollama list
```

Should now show `owen` in the list.

## 🚀 Step 2: Three Ways to Use Owen

### Option 1: Interactive CLI (Easiest)

```bash
tradingagents
```

Follow the prompts:
1. Select ticker (e.g., `NVDA`)
2. Select date (e.g., `2026-01-15`)
3. **LLM Provider:** → Select `Ollama`
4. **Shallow thinking:** → Type `owen:latest`
5. **Deep thinking:** → Type `owen:latest`
6. Continue with analysis

### Option 2: Run Helper Script (Recommended for Quick Testing)

```bash
# Default: NVDA on 2026-01-15
python run_with_owen.py

# Custom ticker and date
python run_with_owen.py MSFT 2026-03-10
```

### Option 3: Python Code (for Integration/Development)

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Configure Owen
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "owen:latest"
config["quick_think_llm"] = "owen:latest"

# Run analysis
ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")

print(decision)
```

## 🎯 Quick Decisions

**Fastest testing** (2-5 min): Use smaller models first
```python
config["deep_think_llm"] = "gemma4:e4b"
config["quick_think_llm"] = "gemma4:e4b"
```

**Best quality** (10-30 min): Use Owen
```python
config["deep_think_llm"] = "owen:latest"
config["quick_think_llm"] = "owen:latest"
```

**Balanced** (5-15 min): Mix models
```python
config["quick_think_llm"] = "gemma4:e4b"       # Fast
config["deep_think_llm"] = "owen:latest"       # Quality
```

## 🔍 Check Setup

```bash
# Verify Ollama is running
curl http://localhost:11434/api/tags

# Check available models
ollama list

# Test Owen responds
ollama run owen "What is machine learning in one sentence?"
```

## 📚 Additional Resources

- Full setup guide: `OLLAMA_SETUP.md`
- Detailed examples: `example_owen_config.py`
- Helper script: `run_with_owen.py`
- Main example: `main.py`

## ❓ Troubleshooting

**"Connection refused"**
```bash
# Start Ollama if not running
ollama serve
```

**"Model not found"**
```bash
# Pull the model
ollama pull owen

# Verify
ollama list
```

**"Out of memory"**
- Owen may require 8GB+ RAM
- Try a smaller model: `ollama pull mistral` or `ollama pull neural-chat`
- Or use mixed models (gemma4 for quick, owen for deep)

**"Very slow responses"**
- First run loads the model into memory (1-2 min)
- Subsequent requests are faster
- Check CPU/GPU usage: `top` or Activity Monitor

## 🎮 Next Steps

1. Pull Owen: `ollama pull owen`
2. Test with CLI: `tradingagents` and select Ollama
3. Test script: `python run_with_owen.py NVDA 2026-01-15`
4. Integrate into your own code using the config pattern

Enjoy using Owen with TradingAgents! 🚀
