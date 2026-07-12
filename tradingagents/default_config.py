import os

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings — defaults to the cheapest local Qwen 2.5 (Ollama) model
    "llm_provider": os.getenv("LLM_PROVIDER", "ollama"),
    "deep_think_llm": os.getenv("DEEP_THINK_LLM", "qwen2.5:1.5b"),
    "quick_think_llm": os.getenv("QUICK_THINK_LLM", "qwen2.5:1.5b"),
    # Optional per-tier provider override for a hybrid setup, e.g. local Ollama
    # for the high-volume quick agents and Hugging Face (or any provider) for
    # the deep/reasoning agents. When unset, both tiers use `llm_provider`.
    # Example hybrid: LLM_PROVIDER=ollama, DEEP_THINK_PROVIDER=huggingface,
    #   DEEP_THINK_LLM=deepseek-ai/DeepSeek-V3-0324 (needs HF_TOKEN).
    "deep_think_provider": os.getenv("DEEP_THINK_PROVIDER") or None,
    "quick_think_provider": os.getenv("QUICK_THINK_PROVIDER") or None,
    "llm_fallback_enabled": os.getenv("LLM_FALLBACK_ENABLED", "true").lower() == "true",
    "llm_prefer_fallback": os.getenv("LLM_PREFER_FALLBACK", "true").lower() == "true",
    "fallback_llm_provider": os.getenv("FALLBACK_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "ollama")),
    "fallback_deep_think_llm": os.getenv("FALLBACK_DEEP_THINK_LLM", "qwen2.5:1.5b"),
    "fallback_quick_think_llm": os.getenv("FALLBACK_QUICK_THINK_LLM", "qwen2.5:1.5b"),
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        # Comma-separated priority chain. Router tries each vendor in order and
        # falls back on any exception OR error-string return.
        "core_stock_apis": "tradingview,mt5,yfinance",
        "technical_indicators": "tradingview,yfinance",
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # Trading mode: "paper" (demo) or "live" trading.
    # Default is "live" so the dashboard reflects the connected MT5 account; the
    # actual broker (demo vs real) is determined by the MT5 terminal you attach
    # to, not by this flag. Auto-trading still requires explicit opt-in via
    # TRADINGAGENTS_AUTO_TRADE.
    "trading_mode": os.getenv("TRADING_MODE", "live").lower(),
    # Watchlist monitoring: symbols to track and their check interval (hours)
    # Defaults are forex/commodity pairs monitored via TradingView
    "watchlist_enabled": os.getenv("WATCHLIST_ENABLED", "true").lower() == "true",
    "watchlist_check_interval_seconds": int(os.getenv("WATCHLIST_CHECK_INTERVAL", "60")),
    "analysis_timeout_seconds": int(os.getenv("TRADINGAGENTS_ANALYSIS_TIMEOUT_SECONDS", "600")),
    # Execution controls. Auto-trading is opt-in and defaults to paper-only.
    "auto_trade_enabled": os.getenv("TRADINGAGENTS_AUTO_TRADE", "false").lower() == "true",
    "auto_trade_paper_only": os.getenv("TRADINGAGENTS_AUTO_TRADE_PAPER_ONLY", "true").lower() == "true",
    # Mock mode: when True, scheduled analyses skip the LLM pipeline and randomly
    # pick BUY or SELL — useful to test the full execution→scoreboard flow quickly.
    "mock_mode_enabled": os.getenv("TRADINGAGENTS_MOCK_MODE", "true").lower() == "true",
    "trade_comment": os.getenv("TRADINGAGENTS_TRADE_COMMENT", "TradingAgent2.0"),
    "max_risk_per_trade_percent": float(os.getenv("TRADINGAGENTS_MAX_RISK_PERCENT", "0.5")),
    "max_risk_per_trade_usd": (
        float(os.getenv("TRADINGAGENTS_MAX_RISK_USD"))
        if os.getenv("TRADINGAGENTS_MAX_RISK_USD")
        else None
    ),
    "max_position_size": float(os.getenv("TRADINGAGENTS_MAX_POSITION_SIZE", "0.5")),
    "max_total_volume": float(os.getenv("TRADINGAGENTS_MAX_TOTAL_VOLUME", "2.0")),
    "max_symbol_positions": int(os.getenv("TRADINGAGENTS_MAX_SYMBOL_POSITIONS", "1")),
    "trade_cooldown_minutes": int(os.getenv("TRADINGAGENTS_TRADE_COOLDOWN_MINUTES", "15")),
    "max_consecutive_losses": int(os.getenv("TRADINGAGENTS_MAX_CONSECUTIVE_LOSSES", "3")),
    "max_daily_loss_usd": float(os.getenv("TRADINGAGENTS_MAX_DAILY_LOSS_USD", "500")),
    "min_reward_cost_multiple": float(os.getenv("TRADINGAGENTS_MIN_REWARD_COST_MULTIPLE", "4")),
    "atr_stop_multiplier": float(os.getenv("TRADINGAGENTS_ATR_STOP_MULTIPLIER", "1.25")),
    "setup_filter_enabled": os.getenv("TRADINGAGENTS_SETUP_FILTER_ENABLED", "true").lower() == "true",
    "max_spread_atr_ratio": float(os.getenv("TRADINGAGENTS_MAX_SPREAD_ATR_RATIO", "0.40")),
    "min_volume_ratio": float(os.getenv("TRADINGAGENTS_MIN_VOLUME_RATIO", "0.20")),
    # Market-data bar granularity for the Market Analyst. "auto" (or empty) keeps
    # the legacy date-range-driven picker (M15..D1); an explicit MT5 timeframe
    # such as "M1", "M5", "M15", "H1", "H4", "D1" forces that granularity so we
    # can trade intraday (e.g. BTCUSD on 1-minute bars).
    "market_timeframe": os.getenv("TRADINGAGENTS_MARKET_TIMEFRAME", "auto"),
    # LLM master switch ("Stop Sonnet"). When False, the scheduler skips the LLM
    # analysis pipeline entirely so no tokens are spent. Toggleable from the
    # dashboard; also auto-flipped off when token_budget_max is exceeded.
    "llm_enabled": os.getenv("TRADINGAGENTS_LLM_ENABLED", "true").lower() == "true",
    # Optional hard token budget. 0 (or absent) means unlimited. When the running
    # total (input+output) reaches this, `llm_enabled` latches off automatically.
    "token_budget_max": int(os.getenv("TRADINGAGENTS_TOKEN_BUDGET_MAX", "0") or "0"),
    # Backtest transaction costs (commission + slippage). Forex/commodity specs
    # carry their own per-lot commission in backtesting/data.py; this block is
    # the override source for the equity fallback so backtest Sharpe/return
    # figures (which feed the self-improvement reviewer) are net of frictions.
    "backtest_costs": {
        "equity": {
            "commission_rate": 0.0005,   # 5 bps of notional, per fill
            "min_commission": 1.0,       # USD floor per fill
            "slippage_points": 2.0,      # adverse fill movement in points (0.02 at point=0.01)
        },
    },
}
