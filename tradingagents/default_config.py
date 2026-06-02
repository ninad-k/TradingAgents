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
    # LLM settings — defaults to local Qwen (Ollama) model
    "llm_provider": os.getenv("LLM_PROVIDER", "ollama"),
    "deep_think_llm": os.getenv("DEEP_THINK_LLM", "gemma4:latest"),
    "quick_think_llm": os.getenv("QUICK_THINK_LLM", "gemma4:latest"),
    "llm_fallback_enabled": os.getenv("LLM_FALLBACK_ENABLED", "true").lower() == "true",
    "llm_prefer_fallback": os.getenv("LLM_PREFER_FALLBACK", "true").lower() == "true",
    "fallback_llm_provider": os.getenv("FALLBACK_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "ollama")),
    "fallback_deep_think_llm": os.getenv("FALLBACK_DEEP_THINK_LLM", "gemma4:latest"),
    "fallback_quick_think_llm": os.getenv("FALLBACK_QUICK_THINK_LLM", "gemma4:latest"),
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
    "trade_comment": os.getenv("TRADINGAGENTS_TRADE_COMMENT", "TradingAgent2.0"),
    "max_risk_per_trade_percent": float(os.getenv("TRADINGAGENTS_MAX_RISK_PERCENT", "0.5")),
    "max_risk_per_trade_usd": (
        float(os.getenv("TRADINGAGENTS_MAX_RISK_USD"))
        if os.getenv("TRADINGAGENTS_MAX_RISK_USD")
        else None
    ),
}
