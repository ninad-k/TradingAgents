# MT5 Integration - Quick Start Guide

## What Was Built

Complete MT5 execution engine for TradingAgents with:
- ✅ Decision → Order conversion
- ✅ Risk limit enforcement
- ✅ Semi-automated approvals
- ✅ Position management
- ✅ Complete audit trail

## Quick Start

### 1. Run Tests (Verify Foundation)
```bash
python test_mt5_foundation.py
```
Expected: 5/5 tests pass ✓

### 2. Basic Usage
```python
from tradingagents.brokers import (
    MT5Connector, OrderGenerator, RiskManager, ExecutionEngine
)
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating

# Create connector (uses mock by default)
connector = MT5Connector(account_type="demo", use_mock=True)
connector.connect()

# Create engines
gen = OrderGenerator()
rm = RiskManager(max_daily_loss=500.0)
engine = ExecutionEngine(connector, rm, gen)

# Create a test decision
decision = PortfolioDecision(
    rating=PortfolioRating.BUY,
    executive_summary="Strong uptrend",
    investment_thesis="Technical indicators support entry",
)

# Process decision
pending = engine.process_decision(decision, "EURUSD", "2026-01-15")

if pending:
    print(f"Pending order: {pending.pending_id}")
    print(f"Risk/Reward: 1:{pending.risk_reward_ratio}")
    
    # Approve and execute
    result = engine.approve_order(pending.pending_id)
    print(f"Executed ticket: {result.ticket}")

connector.disconnect()
```

### 3. With User Approval
```python
from tradingagents.brokers import approve_pending_order_cli

# ... (setup code above)

# Interactive approval
executed_id = approve_pending_order_cli(engine)

# Show summary
show_execution_summary(engine)
```

## Module Reference

### MT5Connector
```python
# Create
connector = MT5Connector(
    account_type="demo",      # demo or live
    use_mock=True,            # Use mock or native MT5
    login=123456,             # Optional
    password="pass",          # Optional
    server="ICMarkets-Demo"   # Optional
)

# Connect
connector.connect()

# Get info
account = connector.get_account_info()      # AccountInfo
symbol = connector.get_symbol_info("EURUSD") # SymbolInfo
position = connector.get_position("EURUSD")  # Position

# Trade
result = connector.place_order(order)        # Dict
result = connector.close_position(ticket, vol) # Dict
result = connector.modify_order(ticket, sl, tp) # Dict

# Cleanup
connector.disconnect()
```

### OrderGenerator
```python
gen = OrderGenerator(
    max_risk_percent=2.0,     # Max % of account
    max_risk_usd=None         # Or max USD (overrides %)
)

# Generate order
order = gen.decision_to_order(
    decision=portfolio_decision,
    symbol="EURUSD",
    symbol_info=symbol_info,
    account_info=account_info,
    decision_id="unique_id",
)

# Create pending order
pending = gen.propose_order(
    decision=decision,
    symbol="EURUSD",
    symbol_info=symbol_info,
    account_info=account_info,
    decision_id="unique_id",
)
```

### RiskManager
```python
rm = RiskManager(
    max_daily_loss=500.0,           # USD
    max_drawdown=1000.0,            # USD
    max_open_positions=5,
    trailing_stop_distance=20,      # pips
    max_risk_per_trade_percent=2.0,
)

# Check if order is allowed
allowed, message = rm.can_open_trade(order, account, positions)

# Manage positions
updates = rm.manage_open_positions(positions, connector)

# Get metrics
metrics = rm.get_risk_metrics(account)
```

### ExecutionEngine
```python
engine = ExecutionEngine(
    connector=connector,
    risk_manager=risk_manager,
    order_generator=order_generator,
    approval_mode="semi_auto",  # semi_auto or signal_only
)

# Process decision
pending = engine.process_decision(
    decision=portfolio_decision,
    symbol="EURUSD",
    decision_date="2026-01-15",
)

# Approve/reject
result = engine.approve_order(pending.pending_id)
engine.reject_order(pending.pending_id, "Too risky")

# Manage
updates = engine.manage_positions()

# Query
pending = engine.get_pending_orders()      # List
summary = engine.get_execution_summary()   # Dict
history = engine.get_execution_history()   # List
```

## Data Structures

### MT5Order
```python
from tradingagents.brokers import MT5Order, OrderAction

order = MT5Order(
    symbol="EURUSD",                    # Required
    action=OrderAction.BUY,             # BUY or SELL
    volume=0.5,                         # lots
    entry_price=1.0950,                 # Optional
    stop_loss=1.0920,                   # Optional
    take_profit=1.1050,                 # Optional
    trailing_stop_distance=20,          # pips
    max_holding_time_hours=72,
    max_loss_per_trade=50.0,
    decision_id="NVDA:2026-01-15:abc",
    reason="Strong technical setup",
)
```

### AccountInfo
```python
from tradingagents.brokers import AccountInfo

account = AccountInfo(
    login=123456,
    server="Demo",
    account_type="DEMO",  # DEMO or REAL
    currency="USD",
    balance=10000.0,
    equity=10000.0,
    free_margin=9500.0,
    margin_level=110.0,
)
```

### SymbolInfo
```python
from tradingagents.brokers import SymbolInfo

symbol = SymbolInfo(
    symbol="EURUSD",
    bid=1.0950,
    ask=1.0952,
    spread=2.0,         # pips
    digits=4,
    point=0.0001,
    min_volume=0.01,
    max_volume=1000.0,
    volume_step=0.01,
)
```

## Connection Methods

### Option 1: Mock (Development)
```python
# No dependencies, works on any OS
connector = MT5Connector(account_type="demo", use_mock=True)
```
**Good for:** Testing, development, no real MT5 available

### Option 2: Native MetaTrader5 (Windows/Linux)
```bash
# Install (Windows/Linux only)
pip install MetaTrader5

# Use in code
connector = MT5Connector(
    login=123456,
    password="password",
    server="ICMarkets-Demo"
)
```
**Good for:** Real MT5 trading on Windows/Linux

### Option 3: REST API (Future)
```python
# Coming in Phase D
connector = MT5Connector(
    api_endpoint="http://mt5-server:8080",
    api_key="your_key"
)
```

## Common Workflows

### Workflow 1: Test with Mock
```python
from tradingagents.brokers import *

# Setup (mocked)
connector = MT5Connector(use_mock=True)
connector.connect()

# ... rest of code
```

### Workflow 2: Demo Account (With Real MT5)
```bash
pip install MetaTrader5
```
```python
connector = MT5Connector(
    login=123456,
    password="password",
    server="ICMarkets-Demo"
)
connector.connect()

# ... rest of code
```

### Workflow 3: With TradingAgents
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.brokers import ExecutionEngine

# Get decision from TradingAgents
ta = TradingAgentsGraph(config=config)
state, decision = ta.propagate("NVDA", "2026-01-15")

# Execute
engine.process_decision(decision, "NVDA", "2026-01-15")
```

## Approval Interface

### With Questionary (Interactive)
```bash
pip install questionary  # Optional, for better UI
```
```python
from tradingagents.brokers import approve_pending_order_cli

executed_id = approve_pending_order_cli(engine)
```

### Without Questionary (Simple Input)
```python
# Falls back to text input automatically
executed_id = approve_pending_order_cli(engine)
```

## Configuration

In `default_config.py`:
```python
DEFAULT_CONFIG.update({
    "enable_mt5_execution": False,           # Off by default (safety)
    "mt5_account_type": "demo",              # demo or live
    "mt5_max_daily_loss": 500.0,             # USD
    "mt5_max_drawdown": 1000.0,              # USD
    "mt5_max_open_positions": 5,
    "mt5_max_risk_per_trade_percent": 2.0,   # Max % per trade
    "mt5_trailing_stop_distance": 20,        # pips
    "mt5_approval_mode": "semi_auto",        # Require approval
})
```

## Files & Structure

```
tradingagents/brokers/
├── models.py           (Data structures)
├── mt5_connector.py    (MT5 connection)
├── order_generator.py  (Decision → Order)
├── risk_manager.py     (Risk enforcement)
├── execution_engine.py (Orchestrator)
├── approval_cli.py     (User approval)
└── __init__.py         (Exports)
```

## Troubleshooting

### Issue: "MetaTrader5 not found"
- You're on macOS or mock connector is being used (this is OK)
- Install on Windows/Linux if you want native MT5
- Otherwise use mock connector for testing

### Issue: "Connection refused"
- MetaTrader 5 terminal not running
- Check credentials (login, password, server)
- Make sure terminal is open on the same machine

### Issue: "Symbol not found"
- Symbol name is incorrect
- Try: "EURUSD" not "eur/usd"
- Verify symbol exists in your broker's symbol list

### Issue: "Insufficient margin"
- Position size is too large
- Reduce position size or add margin
- Check account leverage settings

## Next Steps

1. **Run tests**: `python test_mt5_foundation.py`
2. **Choose setup**:
   - Mock (instant, any OS): `use_mock=True`
   - Native MT5 (real trading): Install on Windows/Linux
3. **Read the docs**:
   - `MT5_IMPLEMENTATION_SUMMARY.md` - Full details
   - Code docstrings - Implementation details
4. **Integration**: Phase C coming soon

## Support

- Full implementation: `MT5_IMPLEMENTATION_SUMMARY.md`
- Test suite: `test_mt5_foundation.py`
- Code docstrings: Each module has detailed documentation
- Examples: Check the usage examples above

---

**Phase A Complete!** Ready for Phase B-G integration.
