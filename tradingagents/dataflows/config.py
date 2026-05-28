import tradingagents.default_config as default_config
from typing import Dict, Optional

# Use default config but allow it to be overridden
_config: Optional[Dict] = None


def initialize_config():
    """Initialize the configuration with default values."""
    global _config
    if _config is None:
        _config = default_config.DEFAULT_CONFIG.copy()


def set_config(config: Dict):
    """Update the configuration with custom values."""
    global _config
    if _config is None:
        _config = default_config.DEFAULT_CONFIG.copy()
    _config.update(config)


def get_config() -> Dict:
    """Get the current configuration."""
    if _config is None:
        initialize_config()
    return _config.copy()


# Initialize with default config
initialize_config()


def apply_backtest_asof(date_str: str) -> str:
    """Clamp a tool's end/current date to the active backtest as-of date.

    During a backtest the controller sets ``backtest_as_of`` so the agents
    cannot read bars past the bar currently being decided. ISO dates compare
    lexicographically, so ``min`` is correct.
    """
    as_of = get_config().get("backtest_as_of")
    if as_of and date_str and date_str > as_of:
        return as_of
    return date_str
