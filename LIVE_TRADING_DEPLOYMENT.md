# Live Trading Deployment Guide - Phase G

## ⚠️ CRITICAL: READ THIS BEFORE GOING LIVE

**This guide covers the transition from demo to live trading. Proceed with extreme caution.**

## Pre-Deployment Checklist

### 1. Demo Account Validation (Minimum 2 weeks)

- [ ] Run 50+ test executions on demo
- [ ] Achieve >60% decision approval rate
- [ ] Average position held 3+ days without forced closure
- [ ] No margin calls or account issues
- [ ] Execution logs reviewed and validated
- [ ] Decision outcomes tracked and analyzed
- [ ] Risk limits never exceeded
- [ ] No unexpected system errors

### 2. System Readiness

- [ ] All modules tested and working
- [ ] Logging enabled and verified
- [ ] Monitoring dashboard operational
- [ ] Backup systems configured
- [ ] Recovery procedures documented
- [ ] Emergency shutdown procedures tested
- [ ] MT5 connection stable for 24+ hours

### 3. Account Setup (Live)

- [ ] Live account created with broker
- [ ] Initial capital: $1000 minimum (larger recommended)
- [ ] Leverage set appropriately (1:10 recommended for safety)
- [ ] Account type: Standard (not micro)
- [ ] Two-factor authentication enabled
- [ ] IP whitelist configured
- [ ] Recovery email/phone set up

### 4. Risk Management Configured

- [ ] Daily loss limit: 2% of account
- [ ] Max drawdown: 5% of account
- [ ] Max positions: 3 (very conservative initially)
- [ ] Max risk per trade: 0.5% (smaller than demo!)
- [ ] Trailing stop: 20 pips enabled
- [ ] Time-based exits: 48 hours max hold

### 5. Monitoring Setup

- [ ] Real-time dashboard running
- [ ] Alert system configured
- [ ] Email/SMS notifications enabled
- [ ] Slack webhook configured (if available)
- [ ] Log aggregation set up
- [ ] Performance dashboard accessible

### 6. Documentation Complete

- [ ] Operations manual written
- [ ] Emergency procedures documented
- [ ] Escalation contacts listed
- [ ] Regular audit schedule set
- [ ] Decision review process established

## Deployment Steps

### Step 1: Dry Run (Day 1)

```python
# Test with live account but no actual execution

from tradingagents.brokers import MT5Connector, ExecutionEngine

# Connect to live (but don't execute)
connector = MT5Connector(
    login=YOUR_LIVE_LOGIN,
    password=YOUR_PASSWORD,
    server="ICMarkets-Live",
    use_mock=False
)

if connector.connect():
    account = connector.get_account_info()
    print(f"Connected: ${account.balance}")
    
    # Test only - don't call approve_order()
    # Just verify connection and data retrieval
```

**Verify:**
- Connection successful
- Account info reads correctly
- Symbol info retrieves correctly
- No errors in logs

### Step 2: First Real Trade (Day 2-3)

**Constraints:**
- Only 1 pending order at a time
- Max position: 0.1 lots (micro position)
- Only on EURUSD (most liquid)
- Only after 08:00 UTC (active trading hours)
- Maximum 1 trade per day
- MUST use stop losses

**Process:**
1. Run TradingAgents analysis
2. Review pending order carefully
3. Check account health
4. Review all risk metrics
5. ONLY execute if absolutely confident
6. Monitor position for full duration
7. Close position manually to test close logic
8. Document outcome

### Step 3: Gradual Ramp-Up (Week 2-4)

**Week 2:**
- Max position: 0.2 lots
- Max 2 trades per day
- 2 symbols (EURUSD, GBPUSD)
- Daily review mandatory

**Week 3:**
- Max position: 0.3 lots
- Max 3 trades per day
- 3 symbols
- Twice-weekly review

**Week 4:**
- Max position: 0.5 lots
- Up to 5 trades per day
- 4-5 symbols
- Weekly comprehensive review

### Step 4: Normal Operations (After 4 weeks)

Only proceed if:
- Account hasn't had margin call
- Win rate >50%
- Approval rate >60%
- No system errors
- All monitoring working

**Operating Constraints:**
- Max position size: 1.0 lot
- Max open positions: 5
- Daily loss limit: 2% of equity
- Max drawdown: 5% of equity
- Regular 1-week audits

## Monitoring During Live Trading

### Daily Tasks (Before Market Open)

```python
from tradingagents.brokers import ExecutionAnalytics
from tradingagents.brokers.safety_validator import SafetyValidator

# Check account health
account = connector.get_account_info()
healthy, msg = SafetyValidator.validate_account_health(account)
print(f"Account health: {msg}")

# Review pending orders
pending = engine.get_pending_orders()
print(f"Pending orders: {len(pending)}")

# Get analytics
analytics = ExecutionAnalytics()
metrics = analytics.get_performance_metrics("day")
print(f"Today's executions: {metrics['executions']}")
```

### During Trading Hours

- Check dashboard every 30 minutes
- Monitor margin level continuously
- Be ready to manually close positions if needed
- Watch for unusual price movements
- Alert if daily loss limit approaching

### End of Day Review

```python
# Review executions
summary = engine.get_execution_summary()
print(f"Executions: {summary['executed']}")
print(f"Risk today: ${summary['total_at_risk']:.2f}")

# Check for issues
history = engine.get_execution_history()
# Review for any errors or failures

# Export logs
analytics.export_to_csv(f"trading_log_{date}.csv")
```

## Emergency Procedures

### If Margin Level Drops Below 150%

1. STOP new executions immediately
2. Manual close largest losing position
3. Wait for confirmation
4. Reassess risk limits
5. DO NOT resume trading until margin >200%

### If Daily Loss Exceeds 1%

1. PAUSE execution system
2. Review all open positions
3. Close 50% of positions
4. Document why limit exceeded
5. Adjust strategy before resuming

### If System Error Occurs

1. Disconnect from MT5 (pull network cable if needed)
2. DO NOT attempt automatic recovery
3. Call support line immediately
4. Manually close all positions
5. Review logs to understand error
6. Only resume after root cause identified

### If Experiencing Margin Call

1. IMMEDIATELY CLOSE ALL POSITIONS
2. Contact broker support
3. Add funds if possible
4. Document incident thoroughly
5. STOP TRADING for 7+ days
6. Complete post-mortem review
7. Update risk limits and procedures

## Performance Targets

| Metric | Target | Acceptable Range |
|--------|--------|------------------|
| Approval Rate | >70% | 60-80% |
| Win Rate | >55% | 50-60% |
| Avg Risk/Reward | 1:2 | 1:1.5 to 1:2.5 |
| Max Drawdown | <5% | <10% |
| Sharpe Ratio | >0.5 | >0.2 |
| Sortino Ratio | >1.0 | >0.5 |

## Weekly Review Process

Every Friday (market close):

1. **Performance Review** (30 min)
   - Executed trades: WIN, LOSS, BREAKEVEN
   - Decision accuracy
   - Risk/Reward achieved vs. projected

2. **System Health** (15 min)
   - Execution logs review
   - Any error conditions
   - Connectivity stability

3. **Risk Metrics** (15 min)
   - Max drawdown hit
   - Largest loss
   - Margin level minimums

4. **Decision Log** (30 min)
   - Review all decisions made
   - Compare against outcomes
   - Identify patterns

5. **Documentation** (15 min)
   - Update operations log
   - Note any changes
   - Backup all data

## Monthly Deep Dive

First Monday of month (2 hours):

1. Statistical analysis of all trades
2. Strategy effectiveness evaluation
3. Risk management review
4. System performance audit
5. Decision model accuracy assessment
6. Update trading plan if needed

## Quarterly Audit

Every 3 months (half day):

1. Complete strategy review
2. Drawdown analysis
3. Market condition assessment
4. Competitor/alternative strategies evaluation
5. System security audit
6. Risk framework review
7. Update deployment if needed

## Deployment Configuration

### Environment Variables

```bash
# .env or .env.live
MT5_ACCOUNT_TYPE=live
MT5_LOGIN=YOUR_LOGIN
MT5_PASSWORD=YOUR_PASSWORD
MT5_SERVER=ICMarkets-Live

# Risk Management
MT5_MAX_DAILY_LOSS=100.0
MT5_MAX_DRAWDOWN=250.0
MT5_MAX_POSITIONS=3
MT5_TRAILING_STOP=20

# Approval
MT5_APPROVAL_MODE=semi_auto
MT5_AUTO_APPROVE=false  # NEVER true in live!

# Monitoring
MT5_MONITORING_ENABLED=true
MT5_ALERT_EMAIL=your@email.com
MT5_SLACK_WEBHOOK=https://hooks.slack.com/...
```

### Starting Live Deployment

```python
from tradingagents.brokers import MT5Connector, ExecutionEngine
from tradingagents.brokers.safety_validator import SafetyValidator

# Load config
import os
from dotenv import load_dotenv
load_dotenv('.env.live')

# Validate setup
SafetyValidator.print_safety_guide()

# Initialize
connector = MT5Connector(
    login=int(os.getenv('MT5_LOGIN')),
    password=os.getenv('MT5_PASSWORD'),
    server=os.getenv('MT5_SERVER'),
)

# Verify connection
if not connector.connect():
    print("FAILED TO CONNECT - STOPPING")
    exit(1)

# Check account
account = connector.get_account_info()
print(f"Connected to live account {account.login}")
print(f"Balance: ${account.balance}")

# Validate account health
healthy, msg = SafetyValidator.validate_account_health(account)
if not healthy:
    print(f"ACCOUNT NOT HEALTHY: {msg}")
    print("Fix account before proceeding")
    exit(1)

print("✓ All safety checks passed")
print("✓ Ready for live trading")
```

## Support Escalation

**If you experience:**

1. **Margin Call**
   - Contact broker immediately
   - Have funds ready to deposit
   - Consider reducing position size permanently

2. **Unusual Price Movement**
   - Check if news released
   - Review your positions
   - Don't panic trade
   - Consider closing if uncomfortable

3. **System Error**
   - Document exact error
   - Stop execution immediately
   - Review logs
   - Contact support with logs

4. **Large Unexpected Loss**
   - STOP trading immediately
   - Review what happened
   - Document thoroughly
   - Do root cause analysis
   - Only resume after understanding

## Success Indicators

### After 1 Month

- Account still solvent
- No margin calls
- Daily loss limit never hit
- >50 executed trades
- Win rate 50%+

### After 3 Months

- Cumulative P&L positive
- Drawdown <5%
- Approval rate >60%
- Win rate improving
- Consistent strategy

### After 6 Months

- Profitable track record
- Risk limits never exceeded
- Reliable execution
- Decision model validated
- Ready to scale carefully

## Scaling to Larger Positions

Only after 6+ months of consistent profitability:

1. Increase max position by 25%
2. Observe for 2 weeks
3. If successful, increase again
4. Maximum increase: double position size
5. Always maintain 1-2% risk per trade

## Conclusion

Live trading is where theory meets reality. The systems in place are designed to:

1. **Protect Your Capital** - Risk limits keep losses small
2. **Validate Decisions** - Approval process ensures quality
3. **Monitor Continuously** - Dashboards catch problems
4. **Enable Recovery** - Procedures guide emergency response

**Remember:** The goal is not to make maximum profit in minimum time. The goal is sustainable, consistent, profitable trading with rigorous risk control.

Start small, validate thoroughly, scale carefully, and monitor continuously.

Good luck with live trading! 🚀
