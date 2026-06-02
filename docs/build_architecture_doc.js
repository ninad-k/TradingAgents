// Build the TradingAgents Architecture & Trade Flow Word document.
const path = require('path');
const fs = require('fs');

const NODE_MODULES = 'C:\\Users\\Ninad\\AppData\\Roaming\\npm\\node_modules';
const docx = require(path.join(NODE_MODULES, 'docx'));

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageBreak, Header, Footer, PageNumber, ImageRun,
} = docx;

const SCHEMA_IMAGE_PATH = path.resolve(__dirname, "..", "assets", "schema.png");

// --- helpers ---
const cellBorder = { style: BorderStyle.SINGLE, size: 1, color: "BFBFBF" };
const borders = { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120 },
    ...opts,
    children: [new TextRun({ text })],
  });
}

function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
}
function h3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });
}

function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { after: 60 },
    children: [new TextRun(text)],
  });
}

function bulletBold(boldText, restText, level = 0) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { after: 60 },
    children: [
      new TextRun({ text: boldText, bold: true }),
      new TextRun({ text: restText }),
    ],
  });
}

function numbered(text, level = 0) {
  return new Paragraph({
    numbering: { reference: "numbers", level },
    spacing: { after: 60 },
    children: [new TextRun(text)],
  });
}

function code(text) {
  return new Paragraph({
    spacing: { after: 120 },
    shading: { fill: "F2F2F2", type: ShadingType.CLEAR },
    children: [new TextRun({ text, font: "Consolas", size: 20 })],
  });
}

function headerCell(text, width) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA }, margins: cellMargins,
    shading: { fill: "D9E2F3", type: ShadingType.CLEAR },
    children: [new Paragraph({ children: [new TextRun({ text, bold: true })] })],
  });
}

function bodyCell(text, width) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA }, margins: cellMargins,
    children: [new Paragraph({ children: [new TextRun(text)] })],
  });
}

function twoColTable(rows, leftWidth = 2880, rightWidth = 6480) {
  const total = leftWidth + rightWidth;
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: [leftWidth, rightWidth],
    rows: [
      new TableRow({
        tableHeader: true,
        children: [headerCell(rows.header[0], leftWidth), headerCell(rows.header[1], rightWidth)],
      }),
      ...rows.body.map(r => new TableRow({
        children: [bodyCell(r[0], leftWidth), bodyCell(r[1], rightWidth)],
      })),
    ],
  });
}

// --- content ---

const titlePara = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 240 },
  children: [new TextRun({ text: "TradingAgents", bold: true, size: 56 })],
});

const subtitle = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 120 },
  children: [new TextRun({ text: "System Architecture & Trade Execution Flow", size: 32 })],
});

const metaPara = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 480 },
  children: [new TextRun({ text: "Internal reference document — June 2026", italics: true, color: "595959" })],
});

const children = [
  titlePara, subtitle, metaPara,

  // 1. Overview
  h1("1. Overview"),
  p("TradingAgents is a multi-agent LLM framework that mirrors how a real trading desk reaches a buy / hold / sell decision. Instead of a single model producing a verdict, the system splits the task across specialised analyst, researcher, trader, risk and portfolio-manager agents that pass structured state through a LangGraph workflow. When operating in live mode, the portfolio manager's decision is forwarded to a broker execution layer (MetaTrader 5 by default) where it is risk-checked, queued for human approval, and submitted to the market."),
  p("The framework is provider-agnostic: any supported LLM backend (OpenAI, Anthropic, Google, xAI, DeepSeek, Qwen, GLM, OpenRouter, Azure OpenAI, or local Ollama) can drive the agents. State, debate transcripts, and reflections are persisted so each new run carries forward lessons from prior decisions on the same ticker."),

  // 2. High-level architecture
  h1("2. High-level architecture"),
  p("The diagram below shows how raw data flows through the agent layers and into execution: market, social, news, and fundamentals feeds enter the analyst side, the researcher team runs a bullish vs. bearish debate, the trader assembles a transaction proposal, the risk management team evaluates it, and the portfolio manager produces the final decision that is sent to the broker for execution."),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 240 },
    children: [new ImageRun({
      type: "png",
      data: fs.readFileSync(SCHEMA_IMAGE_PATH),
      transformation: { width: 620, height: 200 },
      altText: {
        title: "TradingAgents architecture diagram",
        description: "End-to-end flow from market / social / news / fundamentals data sources through the bullish-bearish researcher team, trader, risk management team, portfolio manager, and execution.",
        name: "schema",
      },
    })],
  }),
  p("The codebase is organised as a Python package under tradingagents/ with the following primary modules:"),
  twoColTable({
    header: ["Module", "Responsibility"],
    body: [
      ["agents/", "Analyst, researcher, trader, risk, and portfolio-manager agent definitions and their structured-output schemas."],
      ["graph/", "LangGraph wiring: node setup, conditional routing, propagation, reflection, signal processing, checkpointing."],
      ["dataflows/", "Market data adapters (Yahoo Finance, Finnhub, Alpha Vantage, news/sentiment feeds) with on-disk caching."],
      ["llm_clients/", "Provider abstraction that returns a LangChain-compatible chat model for each backend."],
      ["brokers/", "Live execution layer: MT5 connector, REST adapter, order generator, risk manager, safety validator, approval CLI, execution engine."],
      ["backtesting/", "Historical replay harness and performance metrics (daily v1; see backtesting docs for caveats)."],
      ["monitor/ and frontend/", "Dashboard backend and React UI for inspecting runs, decisions, and open positions."],
      ["api/ and cli/", "FastAPI service and Typer-based interactive CLI entry points."],
    ],
  }),

  p(""),
  p("At runtime the entry point (cli/main.py, run_trading_analysis.py, or the TradingAgentsGraph class itself) instantiates a TradingAgentsGraph with a config dictionary. The graph is built once, then propagate(ticker, date) walks the agents over the requested symbol and returns a structured decision."),

  // 3. Agent layers
  h1("3. Agent layers"),
  p("Each layer feeds the next through a shared AgentState object. Analyst output becomes researcher input; the researcher debate informs the trader proposal; the trader proposal is stress-tested by the risk team; the portfolio manager has the final word."),

  h2("3.1 Analyst team"),
  bulletBold("Fundamentals analyst — ", "evaluates financial statements, ratios, insider transactions, and balance-sheet quality."),
  bulletBold("Sentiment analyst — ", "scores social media and public sentiment around the ticker."),
  bulletBold("News analyst — ", "scans global news and macro indicators for events that move the symbol."),
  bulletBold("Market / technical analyst — ", "computes indicators (MACD, RSI, moving averages, etc.) and flags chart patterns."),
  p("Each analyst can be enabled or disabled via the selected_analysts argument to TradingAgentsGraph. Tool nodes (get_stock_data, get_indicators, get_fundamentals, get_news, get_insider_transactions, get_global_news, ...) are wired into the graph so analysts can pull data on demand rather than receiving a pre-fetched blob."),

  h2("3.2 Researcher team"),
  p("Two researchers — a bullish and a bearish one — read the analyst reports and run a structured debate for max_debate_rounds (configurable). The Research Manager produces a synthesised investment thesis using a typed output schema, so downstream agents receive structured fields rather than free text."),

  h2("3.3 Trader agent"),
  p("The trader consumes the analyst reports and the investment thesis and proposes a concrete trade: side (buy / hold / sell), conviction, and a brief justification. It emits a TraderProposal with a typed schema."),

  h2("3.4 Risk management team"),
  p("Three risk perspectives (aggressive, neutral, conservative) debate the trader's proposal across max_risk_discuss_rounds. They consider volatility, position size, drawdown, and overall portfolio exposure."),

  h2("3.5 Portfolio manager"),
  p("The portfolio manager reads the trader proposal and the risk debate, then emits a final PortfolioDecision (structured output): action, conviction, rating on the 5-tier scale, position sizing intent, and rationale. This is the object that downstream backtesting or live execution consumes."),

  // 4. LangGraph workflow
  h1("4. LangGraph workflow"),
  p("The graph is assembled in tradingagents/graph/setup.py and orchestrated by trading_graph.py:"),
  numbered("GraphSetup builds nodes for each enabled analyst, the bull/bear researchers, the research manager, the trader, the three risk debaters, and the portfolio manager."),
  numbered("ConditionalLogic adds the routing edges, including the loops for the bull/bear debate and the risk debate."),
  numbered("Propagator owns the initial state and drives propagate(ticker, date), starting the graph at the first analyst and ending after the portfolio manager."),
  numbered("Reflector runs after a propagation: it computes the realised return vs. SPY (alpha), writes a one-paragraph reflection into the decision log at ~/.tradingagents/memory/trading_memory.md, and primes future runs with the most recent same-ticker decisions plus cross-ticker lessons."),
  numbered("SignalProcessor extracts the final trading signal from the portfolio manager's structured output."),
  numbered("Checkpointer (opt-in via --checkpoint) saves state to a per-ticker SQLite database after each node, so an interrupted run resumes from the last successful step instead of restarting."),

  // 5. Trade execution flow
  h1("5. How a trade is taken"),
  p("End-to-end, a single trade decision moves through three phases: analysis, broker preparation, and execution."),

  h2("5.1 Phase 1 — Analysis (decision generation)"),
  numbered("The user invokes the CLI, the API, or the TradingAgentsGraph.propagate() method with a ticker and analysis date."),
  numbered("Each enabled analyst node is executed in turn. Analyst nodes call tool functions to fetch fundamentals, indicators, news, and sentiment data; results are cached on disk so repeat runs are cheap."),
  numbered("The bull and bear researchers read the analyst reports and run their debate for the configured number of rounds. The Research Manager emits a structured investment thesis."),
  numbered("The trader agent emits a structured TraderProposal."),
  numbered("The three risk agents debate the proposal; the portfolio manager reads everything and emits a structured PortfolioDecision — action, conviction, sizing intent, and rationale."),
  numbered("The signal processor extracts the final action, the reflector logs realised performance vs. SPY for prior decisions, and the decision is written to the persistent decision log."),

  h2("5.2 Phase 2 — Broker preparation (live mode)"),
  p("In live mode the PortfolioDecision is handed to the ExecutionEngine in tradingagents/brokers/execution_engine.py. The engine orchestrates the broker side of the workflow:"),
  numbered("OrderGenerator converts the PortfolioDecision into a concrete broker order (MT5Order or REST equivalent). It applies the instrument-specific pip value when sizing positions."),
  numbered("RiskManager checks the order against per-trade and account-level limits: max position size, max open exposure, max drawdown, blocked symbols, and minimum equity."),
  numbered("SafetyValidator runs additional sanity checks on the order payload (symbol exists, spread within tolerance, market open, account in good standing)."),
  numbered("If approval_mode is semi_auto, a PendingOrder is queued and surfaced via the approval CLI / dashboard for human confirmation. If approval_mode is signal_only, the engine stops here and only emits a proposed order; nothing is sent to the broker."),

  h2("5.3 Phase 3 — Execution and tracking"),
  numbered("Once approved, the connector (MT5Connector for MetaTrader 5, or RestApiConnector for HTTP brokers) submits the order to the venue and captures the broker fill receipt."),
  numbered("An ExecutionResult is recorded and the engine maintains a live Position cache so subsequent decisions can see current exposure."),
  numbered("The execution log, decision log, and broker analytics are written to disk and exposed via the dashboard API so the user can audit every trade after the fact."),

  // 6. Data and persistence
  h1("6. Data, caching, and persistence"),
  bulletBold("Market data — ", "fetched on demand by tools in dataflows/ and cached under data_cache_dir."),
  bulletBold("Decision log — ", "always-on append-only log at ~/.tradingagents/memory/trading_memory.md (override with TRADINGAGENTS_MEMORY_LOG_PATH). Used by the reflector to inject prior lessons into future runs."),
  bulletBold("Checkpoints — ", "opt-in per-ticker SQLite under ~/.tradingagents/cache/checkpoints/<TICKER>.db. Enable with --checkpoint; reset with --clear-checkpoints."),
  bulletBold("Results directory — ", "structured per-run outputs written under results_dir for the dashboard and downstream tooling."),
  bulletBold("Broker analytics — ", "execution history, P&L, and open positions are persisted by the brokers/analytics module."),

  // 7. Configuration surface
  h1("7. Configuration surface"),
  p("The single source of truth is tradingagents/default_config.py. The most relevant knobs:"),
  twoColTable({
    header: ["Key", "Purpose"],
    body: [
      ["llm_provider", "openai, anthropic, google, xai, deepseek, qwen, glm, openrouter, ollama, azure."],
      ["deep_think_llm / quick_think_llm", "Models used for heavy reasoning vs. quick tool / formatting calls."],
      ["max_debate_rounds", "Bull / bear debate length."],
      ["max_risk_discuss_rounds", "Risk team debate length."],
      ["selected_analysts", "Which analyst nodes are wired into the graph."],
      ["checkpoint_enabled", "Turn LangGraph checkpoint resume on."],
      ["data_cache_dir / results_dir", "On-disk locations for market-data cache and per-run outputs."],
      ["online_tools", "When false the agents only use the local cache; useful for replays and tests."],
    ],
  }),

  // 8. Surfaces
  h1("8. User-facing surfaces"),
  bulletBold("CLI — ", "tradingagents (or python -m cli.main) launches the interactive flow for ticker, date, provider, and depth selection."),
  bulletBold("Python API — ", "instantiate TradingAgentsGraph(config=...) and call .propagate(ticker, date) to get the structured decision."),
  bulletBold("FastAPI service — ", "tradingagents/api/ exposes the framework over HTTP for the dashboard and other clients."),
  bulletBold("Dashboard — ", "React frontend under tradingagents/frontend/ that visualises runs, agent transcripts, open positions, and broker analytics."),
  bulletBold("Backtester — ", "backtester.py and the backtesting/ package replay historical decisions; see docs/superpowers/specs/ for daily-v1 caveats."),

  // 9. Minimal example
  h1("9. Minimal usage example"),
  p("The canonical Python entry point looks like this:"),
  code("from tradingagents.graph.trading_graph import TradingAgentsGraph"),
  code("from tradingagents.default_config import DEFAULT_CONFIG"),
  code(""),
  code("config = DEFAULT_CONFIG.copy()"),
  code("config[\"llm_provider\"] = \"openai\""),
  code("config[\"deep_think_llm\"] = \"gpt-5.4\""),
  code("config[\"quick_think_llm\"] = \"gpt-5.4-mini\""),
  code("config[\"max_debate_rounds\"] = 2"),
  code(""),
  code("ta = TradingAgentsGraph(debug=True, config=config)"),
  code("_, decision = ta.propagate(\"NVDA\", \"2026-01-15\")"),
  code("print(decision)"),
  p("In analysis-only mode the returned decision is what the portfolio manager produced. In live mode the same decision object is what gets handed to ExecutionEngine.process_decision() to be turned into a broker order."),

  // 10. Disclaimer
  h1("10. Disclaimer"),
  p("TradingAgents is a research framework. Outcomes vary with model choice, temperature, data quality, and market conditions, and the framework is not intended as financial, investment, or trading advice. All live trading should run in semi_auto approval mode with conservative risk limits and full broker / account monitoring."),
];

const doc = new Document({
  creator: "TradingAgents",
  title: "TradingAgents — Architecture & Trade Flow",
  styles: {
    default: { document: { run: { font: "Calibri", size: 22 } } }, // 11pt
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Calibri", color: "1F3864" },
        paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Calibri", color: "2E74B5" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Calibri", color: "404040" },
        paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
          { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 1440, hanging: 360 } } } },
        ] },
      { reference: "numbers",
        levels: [
          { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
        ] },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: "TradingAgents — Architecture & Trade Flow", color: "808080", size: 18 })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Page ", color: "808080", size: 18 }),
            new TextRun({ children: [PageNumber.CURRENT], color: "808080", size: 18 }),
          ],
        })],
      }),
    },
    children,
  }],
});

const outPath = path.resolve(__dirname, "TradingAgents_Architecture_and_Trade_Flow.docx");
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(outPath, buf);
  console.log("Wrote " + outPath + " (" + buf.length + " bytes)");
}).catch(err => {
  console.error(err);
  process.exit(1);
});
