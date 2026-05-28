#!/usr/bin/env python3
"""
Quick test of MT5 integration foundation (Phase A).

Tests:
- MT5Connector initialization
- Mock connector functionality
- Models creation
- OrderGenerator basic operations
"""

import sys
from datetime import datetime

# Test imports
try:
    from tradingagents.brokers import (
        MT5Connector, OrderAction, OrderType, MT5Order,
        AccountInfo, SymbolInfo, Position
    )
    from tradingagents.brokers.order_generator import OrderGenerator
    from tradingagents.brokers.risk_manager import RiskManager
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
    print("✓ All imports successful")
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)

def test_connector():
    """Test MT5Connector initialization and connection."""
    print("\n[1/5] Testing MT5Connector...")

    # Use mock connector for testing
    connector = MT5Connector(account_type="demo", use_mock=True)

    if not connector.connect():
        print("✗ Failed to connect")
        return False

    print("✓ Connected (mock mode)")

    # Get account info
    acc = connector.get_account_info()
    if not acc:
        print("✗ Failed to get account info")
        return False

    print(f"✓ Account info: Login={acc.login}, Balance=${acc.balance}, Equity=${acc.equity}")

    # Get symbol info
    sym = connector.get_symbol_info("EURUSD")
    if not sym:
        print("✗ Failed to get symbol info")
        return False

    print(f"✓ Symbol info: EURUSD Bid={sym.bid} Ask={sym.ask} Spread={sym.spread:.1f}pips")

    return True

def test_models():
    """Test Pydantic models."""
    print("\n[2/5] Testing models...")

    # Create an order
    order = MT5Order(
        symbol="EURUSD",
        action=OrderAction.BUY,
        volume=0.1,
        entry_price=1.0950,
        stop_loss=1.0920,
        take_profit=1.1050,
        decision_id="TEST_001",
        reason="Test order",
    )

    print(f"✓ MT5Order created: {order.action} {order.volume} {order.symbol}")

    # Create account info
    acc = AccountInfo(
        login=123456,
        server="Demo",
        account_type="DEMO",
        currency="USD",
        balance=10000.0,
        equity=10000.0,
        free_margin=9500.0,
        margin_level=110.0,
    )

    print(f"✓ AccountInfo created: ${acc.balance}")

    # Create symbol info
    sym = SymbolInfo(
        symbol="EURUSD",
        bid=1.0950,
        ask=1.0952,
        spread=2.0,
        digits=4,
        point=0.0001,
        min_volume=0.01,
        max_volume=1000.0,
        volume_step=0.01,
    )

    print(f"✓ SymbolInfo created: {sym.symbol} Bid={sym.bid} Ask={sym.ask}")

    return True

def test_order_generator():
    """Test OrderGenerator."""
    print("\n[3/5] Testing OrderGenerator...")

    gen = OrderGenerator(max_risk_percent=2.0)

    # Create a mock decision
    decision = PortfolioDecision(
        rating=PortfolioRating.BUY,
        executive_summary="Buy on support with strong uptrend",
        investment_thesis="Technical and fundamental indicators support upside",
        price_target=1.1050,
        time_horizon="3-6 months",
    )

    # Create account and symbol info
    account = AccountInfo(
        login=123456,
        server="Demo",
        account_type="DEMO",
        currency="USD",
        balance=10000.0,
        equity=10000.0,
        free_margin=9500.0,
        margin_level=110.0,
    )

    symbol = SymbolInfo(
        symbol="EURUSD",
        bid=1.0950,
        ask=1.0952,
        spread=2.0,
        digits=4,
        point=0.0001,
        min_volume=0.01,
        max_volume=1000.0,
        volume_step=0.01,
        pip_value_per_lot=10.0,
    )

    # Generate order
    order = gen.decision_to_order(
        decision=decision,
        symbol="EURUSD",
        symbol_info=symbol,
        account_info=account,
        decision_id="TEST_001",
    )

    if not order:
        print("✗ Failed to generate order")
        return False

    print(f"✓ Order generated: {order.action} {order.volume} {order.symbol}")
    print(f"  Entry: {order.entry_price}, SL: {order.stop_loss}, TP: {order.take_profit}")

    return True

def test_risk_manager():
    """Test RiskManager."""
    print("\n[4/5] Testing RiskManager...")

    rm = RiskManager(
        max_daily_loss=500.0,
        max_drawdown=1000.0,
        max_open_positions=5,
        max_risk_per_trade_percent=2.0,
    )

    # Create test order and account
    order = MT5Order(
        symbol="EURUSD",
        action=OrderAction.BUY,
        volume=0.1,
        entry_price=1.0950,
        stop_loss=1.0920,
        take_profit=1.1050,
        decision_id="TEST_001",
        reason="Test",
        max_loss_per_trade=30.0,
    )

    account = AccountInfo(
        login=123456,
        server="Demo",
        account_type="DEMO",
        currency="USD",
        balance=10000.0,
        equity=10000.0,
        free_margin=9500.0,
        margin_level=110.0,
    )

    # Check if trade is allowed
    allowed, message = rm.can_open_trade(order, account, [])

    print(f"✓ Risk check: allowed={allowed}")
    print(f"  {message}")

    # Get risk metrics
    metrics = rm.get_risk_metrics(account)
    print(f"✓ Risk metrics: Balance=${metrics['balance']}, Equity=${metrics['equity']}")

    return True

def test_integration():
    """Test basic integration."""
    print("\n[5/5] Testing integration...")

    # Create connector
    connector = MT5Connector(account_type="demo", use_mock=True)
    connector.connect()

    # Create order generator
    gen = OrderGenerator()

    # Create risk manager
    rm = RiskManager(max_daily_loss=500.0)

    # Get account info
    acc = connector.get_account_info()

    # Create a test decision
    decision = PortfolioDecision(
        rating=PortfolioRating.OVERWEIGHT,
        executive_summary="Moderate buy signal",
        investment_thesis="Good technical setup",
    )

    # Get symbol info
    sym = connector.get_symbol_info("EURUSD")

    # Generate pending order
    pending = gen.propose_order(
        decision=decision,
        symbol="EURUSD",
        symbol_info=sym,
        account_info=acc,
        decision_id="INTEGRATION_TEST",
    )

    if not pending:
        print("✗ Failed to create pending order")
        return False

    print(f"✓ Pending order created: {pending.pending_id}")
    print(f"  Risk/Reward: {pending.risk_reward_ratio:.2f}:1" if pending.risk_reward_ratio else "  N/A")

    # Check if can open trade
    allowed, msg = rm.can_open_trade(pending.order, acc, [])
    print(f"✓ Risk check passed: {allowed}")

    connector.disconnect()
    return True

def main():
    """Run all tests."""
    print("="*70)
    print("MT5 Integration Foundation Test (Phase A)")
    print("="*70)

    tests = [
        ("Connector", test_connector),
        ("Models", test_models),
        ("OrderGenerator", test_order_generator),
        ("RiskManager", test_risk_manager),
        ("Integration", test_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ Error: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "="*70)
    print("Summary")
    print("="*70)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        print("\n✓ All tests passed! Phase A foundation is ready.")
        return 0
    else:
        print("\n✗ Some tests failed. Check output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
