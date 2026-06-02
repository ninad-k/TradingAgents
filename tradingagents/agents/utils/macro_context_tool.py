"""
Macro context tool for the fundamentals analyst.

Stocks have balance sheets; gold, crypto, forex, and indices do not. For those
"macro" instruments the right fundamental lens is rates, USD strength, ETF
flows, and central-bank policy — not corporate financials.

This tool builds a short structured macro brief by pulling a small set of
benchmark tickers from yfinance and packaging the latest prints into a
report the LLM can reason against.

The data sources are intentionally cheap and resilient — if yfinance is
unreachable for a ticker, the row falls back to "n/a" so the rest of the
report still renders.
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Annotated, Dict, List, Optional

from langchain_core.tools import tool

import logging
logger = logging.getLogger(__name__)


# ── Per-mode benchmark ticker lists ────────────────────────────────────────
# Each entry: (yfinance_ticker, short_label, what_it_means_for_the_LLM)
_BENCHMARKS: Dict[str, List[tuple]] = {
    # Real rates dominate gold; USD strength is the inverse correlator.
    "commodity": [
        ("GC=F",      "Gold futures",                   "spot reference for XAUUSD"),
        ("SI=F",      "Silver futures",                 "precious-metals cross-check"),
        ("CL=F",      "WTI crude futures",              "broader commodities tape"),
        ("^TNX",      "US 10Y Treasury yield",          "real-rate proxy — gold falls when this rises"),
        ("DX-Y.NYB",  "US Dollar Index (DXY)",          "USD strength — gold is the inverse"),
        ("^VIX",      "Volatility index",               "risk-off bid for safe-haven flows"),
        ("GLD",       "SPDR Gold Shares ETF",           "retail/institutional gold demand"),
        ("TIP",       "TIPS bond ETF",                  "real-rates / inflation expectations — falling TIP means rising real rates (bearish gold)"),
    ],
    # Crypto: Fed cycle, USD, BTC ETF flows, equity risk appetite.
    "crypto": [
        ("BTC-USD",   "Bitcoin spot (yfinance)",        "spot reference"),
        ("ETH-USD",   "Ethereum spot",                  "broader crypto correlation"),
        ("IBIT",      "iShares Bitcoin Trust ETF",      "institutional spot ETF flows"),
        ("GBTC",      "Grayscale Bitcoin Trust",        "legacy BTC vehicle / outflow pressure"),
        ("^TNX",      "US 10Y Treasury yield",          "real-rate environment"),
        ("DX-Y.NYB",  "US Dollar Index (DXY)",          "USD strength dampens BTC"),
        ("QQQ",       "Nasdaq-100 ETF",                 "risk-on/risk-off proxy"),
        ("^VIX",      "Volatility index",               "macro fear gauge"),
    ],
    # Forex: rate differentials and USD strength dominate.
    "forex": [
        ("DX-Y.NYB",  "US Dollar Index (DXY)",          "USD strength baseline"),
        ("^TNX",      "US 10Y Treasury yield",          "USD rate side"),
        ("^IRX",      "US 3M Treasury yield",           "short-end USD rate"),
        ("EURUSD=X",  "EUR/USD spot",                   "EUR cross-check"),
        ("GBPUSD=X",  "GBP/USD spot",                   "GBP cross-check"),
        ("JPY=X",     "USD/JPY spot",                   "JPY carry-trade proxy"),
        ("^VIX",      "Volatility index",               "risk sentiment / safe-haven flow"),
    ],
    # Indices: yield curve + USD + sector ETF spread.
    "index": [
        ("^GSPC",     "S&P 500 index",                  "broad-market level"),
        ("^NDX",      "Nasdaq-100",                     "tech tilt"),
        ("^DJI",      "Dow Jones Industrial",           "old-economy benchmark"),
        ("^TNX",      "US 10Y Treasury yield",          "discount rate / multiple compression risk"),
        ("DX-Y.NYB",  "US Dollar Index",                "earnings translation risk"),
        ("^VIX",      "Volatility index",               "implied stress"),
    ],
}


def _fetch_latest_close(ticker: str, curr_date: str) -> Optional[tuple]:
    """Return (close, change_pct_5d) from yfinance, or None if unavailable.

    Cheap call — only reads ~10 trading days so the analyst stays fast even
    when pulling 6–8 benchmarks per run.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        end = datetime.strptime(curr_date, "%Y-%m-%d")
    except Exception:
        end = datetime.utcnow()
    start = end - timedelta(days=21)  # 3 calendar weeks to clear holidays
    try:
        hist = yf.Ticker(ticker).history(
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            auto_adjust=False,
        )
    except Exception as e:
        logger.debug("yfinance fetch failed for %s: %s", ticker, e)
        return None
    if hist is None or hist.empty:
        return None
    closes = hist["Close"].dropna()
    if closes.empty:
        return None
    latest = float(closes.iloc[-1])
    # 5-trading-day change for trend context.
    if len(closes) >= 6:
        prior = float(closes.iloc[-6])
        change_pct = (latest - prior) / prior * 100.0 if prior else 0.0
    else:
        change_pct = 0.0
    return latest, change_pct


def _build_report(mode: str, symbol: str, curr_date: str) -> str:
    benchmarks = _BENCHMARKS.get(mode, [])
    if not benchmarks:
        return (
            f"No macro-context profile is configured for instrument mode `{mode}`. "
            f"Treat {symbol} on its technical merits alone and lean on news flow for catalysts."
        )

    rows: List[str] = [
        f"# Macro Context for {symbol}  (mode: {mode}, as of {curr_date})",
        "",
        "| Benchmark | Latest | 5-day change | What it means here |",
        "| --- | ---: | ---: | --- |",
    ]
    for ticker, label, meaning in benchmarks:
        data = _fetch_latest_close(ticker, curr_date)
        if data is None:
            rows.append(f"| {label} (`{ticker}`) | n/a | n/a | {meaning} |")
            continue
        latest, change_pct = data
        sign = "+" if change_pct >= 0 else ""
        rows.append(
            f"| {label} (`{ticker}`) | {latest:,.2f} | {sign}{change_pct:.2f}% | {meaning} |"
        )

    rows += [
        "",
        "## How to use this in your fundamentals report",
        "",
        f"`{symbol}` is a **{mode}** — it has no balance sheet, cash flow, or earnings. "
        "Frame the fundamental view around the macro drivers above:",
        "",
    ]

    if mode == "commodity":
        rows += [
            "- Are real rates (10Y yield minus inflation expectations) rising or falling? "
            "Rising real rates are bearish for non-yielding assets like gold.",
            "- Is DXY strengthening or weakening? Gold is roughly inverse to DXY.",
            "- ETF flows (GLD) — sustained inflows mean institutional accumulation.",
        ]
    elif mode == "crypto":
        rows += [
            "- Bitcoin ETF flows (IBIT) are a fast read on institutional demand.",
            "- Risk-on/risk-off — BTC tracks Nasdaq when liquidity expands.",
            "- DXY direction. A weakening dollar historically lifts BTC.",
        ]
    elif mode == "forex":
        rows += [
            "- Rate differentials drive the pair — compare DXY trend to the cross.",
            "- VIX spikes typically bid the USD and JPY.",
        ]
    elif mode == "index":
        rows += [
            "- Long-end yields (10Y) compete with equity earnings yield; rising yields cap multiples.",
            "- VIX above 20 historically corresponds to short-term equity drawdowns.",
        ]

    rows += [
        "",
        "End your section with a clear stance — bullish / bearish / neutral fundamental backdrop "
        "for the next 1–4 weeks — and the **one** macro variable to watch most closely.",
    ]
    return "\n".join(rows)


@tool
def get_macro_context(
    ticker: Annotated[str, "the symbol being analyzed (e.g. XAUUSD, BTCUSD, EURUSD)"],
    mode: Annotated[str, "instrument mode: commodity, crypto, forex, or index"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Build a macro context brief for non-stock instruments.

    Fetches a short table of benchmark prints (USD index, 10Y yield, related
    ETFs, etc.) appropriate to the instrument mode, plus an interpretation
    framework so the LLM can write a coherent macro-fundamentals section.

    Use this in place of `get_balance_sheet` / `get_income_statement` when the
    symbol is gold, oil, crypto, a currency pair, or an equity index — those
    don't have corporate financials.
    """
    return _build_report((mode or "").lower().strip(), ticker.upper(), curr_date)
