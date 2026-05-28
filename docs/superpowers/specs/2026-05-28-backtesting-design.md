# Backtesting module — design

**Date:** 2026-05-28
**Status:** Approved (design); pending implementation plan
**Scope:** Add a backtesting capability to TradingAgents, ported and adapted from `virattt/ai-hedge-fund` (`src/backtesting/`, MIT-licensed).

## Problem

TradingAgents already drives live capital through `tradingagents/brokers/` (MT5 execution, `OrderGenerator`, risk manager). It has **no backtester**, so the multi-agent ensemble's decisions cannot be validated against history before deployment. This adds one.

## Goals

- Run the existing agent ensemble (`TradingAgentsGraph.propagate`) over a historical date range and produce a portfolio equity curve plus performance metrics (Sharpe, Sortino, max drawdown).
- Support both **US equities (share-based)** and **forex/XAUUSD (lot-based)** through one generic engine.
- For forex, reuse the **live** `OrderGenerator` decision→order path so the backtest exercises the exact sizing/SL/TP logic that gets deployed.
- Make iteration cheap and look-ahead-honest via a disk decision cache and configurable rebalance cadence.

## Non-goals (out of scope for this work)

- The famous-investor persona agents from ai-hedge-fund.
- The persona-style confidence-scored signal-aggregation pattern (may be revisited later, separately).
- Event-driven / tick-level simulation, slippage models beyond spread, portfolio optimization.
- A web UI for backtests (CLI + structured output only).

## Decisions (locked during brainstorming)

1. **Target:** generic engine covering both shares and lots (not stocks-only or forex-only).
2. **Cost handling:** persistent decision cache + configurable rebalance cadence (default weekly).
3. **Position/fill model:** reuse live `OrderGenerator` for forex (synthesize `SymbolInfo`/`AccountInfo` from bars), parallel shares model for equities, both behind a common `PositionModel` interface; SL/TP checked intrabar.

## Architecture

New package: `tradingagents/backtesting/`. Each file has one clear purpose.

| File | Purpose | Origin |
|---|---|---|
| `types.py` | `BacktestConfig`, `Bar`, `Trade`, `Fill`, `PortfolioValuePoint`, `PerformanceMetrics`, `InstrumentSpec` | new |
| `metrics.py` | Sharpe / Sortino / max-drawdown; `annual_trading_days` parameter (252 for daily stocks, configurable for forex/intraday) | lifted ~verbatim from ai-hedge-fund `src/backtesting/metrics.py` (MIT, attributed) |
| `data.py` | `bars(symbol, start, end, timeframe)` over existing `tradingagents/dataflows` (yfinance for stocks, tradingview for forex/XAUUSD); enforces the **as-of cap** | new, wraps existing |
| `position_models.py` | `PositionModel` interface + `EquitySharesModel` and `ForexLotModel` (wraps `OrderGenerator`, synthesizes `SymbolInfo`/`AccountInfo` from bars + simulated equity) | new + reuse of `brokers/order_generator.py` |
| `decision_cache.py` | persist `(symbol, date) → PortfolioDecision` as JSON under `config["data_cache_dir"]` | new |
| `controller.py` | bridge: apply as-of guard → call `TradingAgentsGraph.propagate` → parse `PortfolioDecision` out of `final_state` | new |
| `portfolio.py` | cash / positions / equity / margin / exposures tracking | adapted from ai-hedge-fund |
| `benchmarks.py` | buy-and-hold of the traded instrument (SPY for equities) | adapted |
| `engine.py` | the bar loop, fill simulation, intrabar SL/TP, mark-to-market, equity-point recording | adapted |
| `output.py` | results table / summary rendering | adapted |
| `backtester.py` (repo root, mirroring `main.py`) | CLI entrypoint: `--ticker --start --end --cadence --timeframe --initial-capital` | adapted from `src/backtester.py` |

### Data flow

```
backtester.py (repo root)
  → engine.run()
      for each bar at cadence:
        → controller.decide(symbol, bar_date)
            → as-of guard clamps tool end_date to bar_date
            → decision_cache.get(symbol, bar_date)  (hit → return)
            → TradingAgentsGraph.propagate(symbol, bar_date)
            → parse PortfolioDecision from final_state
            → decision_cache.put(...)
        → position_model.build_order(decision, bar, portfolio_state)
        → engine simulates fill on NEXT bar (open ± half-spread for forex)
        → apply intrabar SL/TP on subsequent bars
        → portfolio.mark_to_market(bar)
        → record PortfolioValuePoint
  → metrics.compute_metrics(values)
  → benchmarks.compare(...)
  → output.render(...)
```

## Key behaviors

### Look-ahead guard (most important invariant)

`get_stock_data(symbol, start_date, end_date)` lets the analyst LLM choose `end_date`, which could exceed the bar date and leak the future. In backtest mode the `controller` sets a flag in `dataflows.config` that **clamps any tool `end_date` to the current bar date**. This invariant gets a dedicated test: a request for data beyond the bar date must return nothing past it.

### Fill model

- A decision made at bar *t* fills at **bar *t+1* open** (no same-bar look-ahead).
- Forex fills apply ± half the spread (buy at ask-side, sell at bid-side) using `InstrumentSpec`.
- SL/TP are checked against each subsequent bar's high/low. If a single bar's range hits **both** SL and TP, assume worst case: **SL first**.
- Gap-through: if a bar opens beyond SL/TP, fill at the open (gap), not the level.
- Time-horizon exit uses `OrderGenerator._parse_time_horizon` to close positions after their stated horizon.

### Position models

- `EquitySharesModel`: integer/fractional shares, long/short, sized as a fraction of equity. No pip/spread machinery.
- `ForexLotModel`: builds a `PortfolioDecision`, synthesizes `SymbolInfo` (bid/ask/spread/point/min/max/step from `InstrumentSpec` + bar close) and `AccountInfo` (from simulated equity), then calls `OrderGenerator.decision_to_order` to get lots + SL/TP. The resulting `MT5Order` is translated into an engine `Fill`/`Trade`.

### Decision cache

- Keyed by `(symbol, date, config-hash)` so changing the model/agents invalidates stale entries.
- Stored as JSON under `data_cache_dir`; serializes the parsed `PortfolioDecision`.
- Cache hit skips the LLM ensemble entirely → re-runs of the same window are free.

### Metrics

- Lifted from ai-hedge-fund: Sharpe and Sortino (annualized via `sqrt(annual_trading_days)`, daily risk-free from `annual_rf_rate`), max drawdown + drawdown date.
- `annual_trading_days` is a parameter: 252 for daily equities; for forex/intraday it is set from the timeframe (e.g. 252 daily, or bars-per-year for intraday).

## Defaults

- **Cadence:** weekly (every 5 daily bars), overridable per run via `--cadence`.
- **InstrumentSpec:** hardcoded table for XAUUSD + major forex pairs to start (pip size, pip value, lot min/max/step); table-driven so new instruments are a one-line addition. Equities use a trivial spec (1 "unit" = 1 share, no pip).

## Testing

- `metrics.py`: known return series → asserted Sharpe / Sortino / max-drawdown values; empty / single-point / zero-variance edge cases.
- `portfolio.py`: cash conservation, realized/unrealized P&L correctness, margin accounting.
- `engine.py` fill logic: t+1 open fill, gap-through SL, both-SL-and-TP-in-one-bar → SL first, time-horizon exit.
- Look-ahead guard: a tool request for `end_date` beyond the bar date returns nothing past the bar date.
- `decision_cache.py`: put/get round-trip, config-hash invalidation, cache hit avoids `propagate`.
- `position_models.py`: `ForexLotModel` produces the same lots/SL/TP as the live `OrderGenerator` for a fixed synthesized `SymbolInfo`/`AccountInfo`.

## Attribution

`metrics.py`, and the structure of `portfolio.py` / `engine.py` / `benchmarks.py` / `output.py`, are adapted from `virattt/ai-hedge-fund` (`src/backtesting/`), MIT-licensed. License/attribution noted in the package.
