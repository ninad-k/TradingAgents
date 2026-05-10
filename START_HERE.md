# TradingAgents with Qwen3.6 - Start Here

Your setup is ready to go! You have a fully configured TradingAgents environment using **Qwen3.6** (Ollama) for financial analysis.

## ✅ Verification

Your setup has been tested and verified working:
- ✓ Qwen3.6 LLM client connection
- ✓ TradingAgentsGraph initialization
- ✓ Ollama server communication

## 🚀 Run Your First Analysis

### Quickest Way (Recommended)

```bash
source .venv/bin/activate
python run_trading_analysis.py
```

**What this does:**
- Analyzes NVDA stock on 2026-01-15
- Uses Qwen3.6 for all reasoning
- Takes 15-25 minutes
- Shows complete trading decision

### Custom Analysis

```bash
# Different ticker and date
python run_trading_analysis.py MSFT 2026-03-10

# Add debate rounds for deeper analysis
python run_trading_analysis.py AAPL 2026-02-15 2
```

### Usage

```bash
python run_trading_analysis.py [TICKER] [DATE] [DEBATE_ROUNDS]

Examples:
  python run_trading_analysis.py                    # Default: NVDA, 2026-01-15
  python run_trading_analysis.py TSLA 2026-02-20   # Custom ticker & date
  python run_trading_analysis.py MSFT 2026-03-01 2 # With more debate rounds
```

## 📊 Expected Output

The analysis will show:
1. **Fundamental Analysis** - Company financials & valuation
2. **Sentiment Analysis** - Market and news sentiment
3. **Technical Analysis** - Price patterns and indicators
4. **News Analysis** - Recent economic events
5. **Debate** - Bullish vs bearish perspectives
6. **Trading Decision** - Buy/Sell/Hold with confidence

Example output snippet:
```
======================================================================
✓ Analysis Complete
======================================================================
Ticker:          NVDA
Date:            2026-01-15
Time Elapsed:    1245.3 seconds (20.8 minutes)
Trading Decision: STRONG BUY - Qwen3.6 recommends buying based on...
======================================================================
```

## 🎯 What Qwen3.6 Does Best

Qwen3.6 (23GB) was chosen because it:
- **Excellent reasoning** - Understands complex financial relationships
- **Good context understanding** - Interprets nuanced news and sentiment
- **Fast enough** - Completes analysis in 15-25 minutes
- **Reliable** - Consistent, stable outputs
- **Financial knowledge** - Good understanding of trading concepts

## 📝 Available Scripts

| Script | Purpose | Command |
|--------|---------|---------|
| `run_trading_analysis.py` | Full trading analysis | `python run_trading_analysis.py` |
| `quick_test.py` | Verify setup works | `python quick_test.py` |
| `example_owen_config.py` | Config examples | See file for patterns |
| `main.py` | Basic example | `python main.py` |

## 🔧 Configuration

All scripts use this Qwen3.6 configuration:

```python
config["llm_provider"] = "ollama"
config["deep_think_llm"] = "qwen3.6:latest"      # Qwen for all thinking
config["quick_think_llm"] = "qwen3.6:latest"     
config["max_debate_rounds"] = 1                   # 1 round default, can increase
```

To modify, edit `run_trading_analysis.py` lines 17-22.

## 💡 Tips

**Faster Testing** (Use Gemma4 instead)
```python
config["deep_think_llm"] = "gemma4:e4b"          # Only 5-10 min
config["quick_think_llm"] = "gemma4:e4b"
```

**Better Analysis** (More debate)
```python
config["max_debate_rounds"] = 2                   # Takes ~40 min
```

**Different Model Mix** (Fast screening + quality analysis)
```python
config["quick_think_llm"] = "gemma4:e4b"         # Quick decisions
config["deep_think_llm"] = "qwen3.6:latest"      # Deep analysis
```

## ❓ Troubleshooting

**"Connection refused" error**
```bash
# Make sure Ollama is running
ollama serve
```

**"Model not found"**
```bash
# Verify qwen3.6 is installed
ollama list

# Check it shows: qwen3.6:latest
```

**Takes very long time**
- First run loads 23GB model into memory (1-2 min)
- Subsequent analyses are faster
- Ensure you have ~24GB available RAM

**Want faster analysis?**
- Use `gemma4:e4b` instead (9.6GB, 5-10 min)
- Reduce `max_debate_rounds` to 0
- Check CPU/GPU usage with Activity Monitor

## 📚 More Documentation

- `OWEN_QUICKSTART.md` - Quick reference
- `OLLAMA_SETUP.md` - Detailed Ollama setup
- `TEST_OWEN_SETUP.md` - Comprehensive testing guide
- `OWEN_SETUP_SUMMARY.md` - Full setup overview
- `example_owen_config.py` - Configuration examples

## 🎮 Next Steps

1. **Run a quick test** (2 min):
   ```bash
   source .venv/bin/activate
   python quick_test.py
   ```

2. **Run first analysis** (20 min):
   ```bash
   source .venv/bin/activate
   python run_trading_analysis.py
   ```

3. **Customize as needed**:
   - Edit `run_trading_analysis.py` for different settings
   - Try different tickers/dates
   - Adjust debate rounds
   - Experiment with model combinations

## ✨ You're All Set!

Your TradingAgents + Qwen3.6 environment is ready. Just run:

```bash
source .venv/bin/activate
python run_trading_analysis.py NVDA 2026-01-15
```

Enjoy your trading analysis! 🚀
