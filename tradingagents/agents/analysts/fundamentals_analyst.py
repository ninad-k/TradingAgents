"""
Mode-aware fundamentals analyst.

Stocks have balance sheets, cashflow, and income statements — the original
behavior. Gold, crypto, forex pairs, and equity indices don't; for those the
analyst loads a macro-context brief (USD strength, real rates, ETF flows,
mode-appropriate cross-asset comparisons) and writes a macro fundamentals
report instead. Same agent role, same downstream debate — the prompt and
tool set adapt to the instrument.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_language_instruction,
)
from tradingagents.agents.utils.macro_context_tool import get_macro_context
from tradingagents.monitor.symbols import detect_symbol_mode


_STOCK_SYSTEM = (
    "You are a researcher tasked with analyzing fundamental information over the past week "
    "about a company. Please write a comprehensive report of the company's fundamental information "
    "such as financial documents, company profile, basic company financials, and company financial "
    "history to gain a full view of the company's fundamental information to inform traders. Make "
    "sure to include as much detail as possible. Provide specific, actionable insights with "
    "supporting evidence to help traders make informed decisions."
    " Make sure to append a Markdown table at the end of the report to organize key points, "
    "organized and easy to read."
    " Use the available tools: `get_fundamentals` for comprehensive company analysis, "
    "`get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
)


def _macro_system(mode: str, symbol: str) -> str:
    """Mode-specific instruction for non-stock instruments."""
    if mode == "commodity":
        focus = (
            "real interest rates (10Y yield trajectory), USD strength (DXY), "
            "central-bank gold reserves and ETF flows (GLD), and inflation expectations"
        )
    elif mode == "crypto":
        focus = (
            "Bitcoin ETF flows (IBIT, GBTC), Fed-rate environment, USD strength, "
            "broader risk appetite (QQQ vs. VIX), and the BTC-to-altcoin relationship"
        )
    elif mode == "forex":
        focus = (
            "rate differentials between the two currencies, central-bank policy stance, "
            "USD index trajectory, and risk-sentiment flows (carry vs. safe-haven)"
        )
    elif mode == "index":
        focus = (
            "long-end yield trajectory and its impact on equity multiples, "
            "USD strength (earnings-translation risk for multinationals), and implied volatility"
        )
    else:
        focus = "macro-rate environment and USD strength"

    return (
        f"You are a macro researcher tasked with the fundamental view on `{symbol}`. "
        f"This is a **{mode}** instrument — it has no balance sheet, cashflow, or earnings, "
        "so do NOT call company-financial tools. Instead, call `get_macro_context` exactly once "
        f"with mode=`{mode}` to fetch the benchmark macro table, then write a focused report on "
        f"{focus}. "
        "Tie every observation to its directional implication for the symbol over the next 1–4 weeks. "
        "End with a clear bullish / bearish / neutral fundamental stance and the single macro "
        "variable most worth watching."
        " Append a Markdown summary table of the key drivers and their current direction."
    )


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        symbol = state["company_of_interest"]
        instrument_context = build_instrument_context(symbol)
        mode = detect_symbol_mode(symbol)

        if mode == "stock":
            tools = [get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement]
            system_message = _STOCK_SYSTEM + get_language_instruction()
        else:
            tools = [get_macro_context]
            system_message = _macro_system(mode, symbol) + get_language_instruction()

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
