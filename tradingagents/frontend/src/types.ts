/**API and component types */

export interface AccountStatus {
  trading_mode: string
  server?: string | null
  account_balance: number
  account_equity: number
  available_margin: number
  total_pnl: number
  total_pnl_percent: number
  win_rate: number
  total_trades: number
  open_trades: number
  closed_trades: number
  largest_win: number
  largest_loss: number
  avg_trade_duration: number
}

export interface Position {
  symbol: string
  quantity: number
  entry_price: number
  current_price: number
  direction: 'long' | 'short'
  unrealized_pnl: number
  unrealized_pnl_percent: number
  entry_time: string
  duration_seconds: number
  comment?: string | null
}

export interface Trade {
  symbol: string
  entry_price: number
  entry_time: string
  exit_price: number | null
  exit_time: string | null
  quantity: number
  direction: 'long' | 'short'
  status: 'open' | 'closed' | 'rejected' | 'failed'
  pnl: number | null
  pnl_percent: number | null
  duration_seconds: number | null
  reason: string | null
  comment?: string | null
}

export interface TokenUsage {
  tokens_in: number
  tokens_out: number
  total: number
  llm_calls: number
  budget_max: number
  llm_enabled: boolean
}

export interface DashboardStatus {
  timestamp: string
  connected: boolean
  account: AccountStatus
  open_positions: Position[]
  recent_trades: Trade[]
  total_positions: number
  total_closed_trades: number
  token_usage?: TokenUsage | null
}

export interface TradeEvent {
  type: string
  symbol?: string
  timestamp: string
  data: Record<string, unknown>
}

export interface WatchlistEntry {
  symbol: string
  display_name: string
  mode: 'forex' | 'commodity' | 'crypto' | 'index' | 'stock'
  interval_hours: number
  interval_minutes?: number
  analysts: string[]
  use_tradingview: boolean
  enabled: boolean
  last_analysis: string | null
  last_decision: string | null
  last_signal: string | null   // "BUY" | "SELL" | "HOLD" | null
  latest_result?: AnalysisResult
  analysis_job?: AnalysisJob
}

export interface AnalysisResult {
  symbol: string
  success: boolean
  signal: string
  decision_text: string
  error: string | null
  execution?: {
    status?: string
    reason?: string
    ticket?: number
    execution_price?: number
    comment?: string
  } | null
  timestamp: string
}

export interface AnalysisEvent {
  type: string
  data: AnalysisResult
  timestamp: string
}

export interface AnalysisJob {
  job_id: string
  symbol: string
  execute_trade: boolean
  status: 'queued' | 'running' | 'completed' | 'failed' | 'timeout'
  message: string
  progress_percent: number
  started_at: string
  updated_at: string
  completed_at: string | null
  timeout_seconds: number
  result?: AnalysisResult | null
  error?: string | null
}

export interface TriggerAnalysisResponse {
  triggered: boolean
  symbol: string
  execute_trade: boolean
  job_id: string
  job: AnalysisJob
  message: string
}

export interface AnalysisTrace {
  symbol: string
  signal: string
  success: boolean
  timestamp: string
  components: {
    market_analyst: string
    sentiment_analyst: string
    news_analyst: string
    fundamentals_analyst: string
    bull_researcher: string
    bear_researcher: string
    research_manager: string
    trader: string
    aggressive_risk: string
    neutral_risk: string
    conservative_risk: string
    portfolio_manager: string
  }
  debates: {
    research: string
    risk: string
  }
  execution?: AnalysisResult['execution'] | null
}

export interface AnalysisFlow {
  id: number
  symbol: string
  signal: string
  decision_text: string | null
  success: boolean
  error: string | null
  params_snapshot: Record<string, unknown> | null
  horizon_hours: number
  decided_at: string
  trace: AnalysisTrace
  trace_created_at?: string | null
  trace_note?: string
  entry_price?: number | null
  exit_price?: number | null
  pnl_pct?: number | null
  evaluated_at?: string | null
  outcome_error?: string | null
}

// ─── Learning loop ─────────────────────────────────────────────────────────

export interface PerSignalStats {
  count: number
  win_rate: number
  mean_pnl_pct: number
}

export interface Scoreboard {
  n_decisions: number
  n_evaluated: number
  win_rate: number | null
  mean_pnl_pct: number | null
  stdev_pnl_pct: number | null
  sharpe: number | null
  max_drawdown_pct: number | null
  total_return_pct: number | null
  per_signal: Record<string, PerSignalStats>
}

export interface DecisionRow {
  id: number
  symbol: string
  signal: string
  decision_text: string | null
  success: boolean
  error: string | null
  params_snapshot: Record<string, unknown> | null
  horizon_hours: number
  decided_at: string
  // From decision_outcomes (LEFT JOIN — may be null)
  entry_price?: number | null
  exit_price?: number | null
  pnl_pct?: number | null
  evaluated_at?: string | null
  outcome_error?: string | null
}

export interface ProposalDiffEntry {
  from: unknown
  to: unknown
}

export interface Proposal {
  id: number
  params: Record<string, unknown>
  diff: Record<string, ProposalDiffEntry> | null
  rationale: string | null
  applied: boolean
  proposed_at: string
  applied_at: string | null
  rejected_at: string | null
  rejection_reason: string | null
  markdown?: string | null
  markdown_path?: string | null
}

export type LearnedParams = Record<string, unknown>
export type Goals = Record<string, unknown>

export interface AppSettings {
  llm_provider: string
  deep_think_llm: string
  quick_think_llm: string
  llm_fallback_enabled: boolean
  llm_prefer_fallback: boolean
  fallback_llm_provider: string
  fallback_deep_think_llm: string
  fallback_quick_think_llm: string
  watchlist_enabled: boolean
  watchlist_check_interval_seconds: number
  analysis_timeout_seconds: number
  auto_trade_enabled: boolean
  auto_trade_paper_only: boolean
  mock_mode_enabled: boolean
  trade_comment: string
  max_risk_per_trade_percent: number
  max_risk_per_trade_usd: number | null
  market_timeframe: string
  llm_enabled: boolean
  token_budget_max: number
}

export interface SettingsResponse {
  settings: AppSettings
  ollama_models: string[]
  settings_path: string
}

/** Single entry from /api/symbols — the broker's symbol catalog. */
export interface BrokerSymbol {
  name: string
  description: string
  path: string
  category: string
  currency_base: string
  currency_profit: string
  digits: number
  visible: boolean
}

export interface BrokerSymbolsResponse {
  count: number
  categories: Record<string, number>
  symbols: BrokerSymbol[]
}

export type FlowComponentKey =
  | 'market_analyst'
  | 'sentiment_analyst'
  | 'news_analyst'
  | 'fundamentals_analyst'
  | 'bull_researcher'
  | 'bear_researcher'
  | 'research_manager'
  | 'trader'
  | 'aggressive_risk'
  | 'neutral_risk'
  | 'conservative_risk'
  | 'portfolio_manager'

export type FlowComponentStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped'

export interface FlowComponentState {
  status: FlowComponentStatus
  /** Short text shown in the architecture node card (≤160 chars). */
  preview: string
  /** Full untruncated output text, rendered in the detail panel. */
  full_text?: string
  updated_at: number
  /** Epoch seconds — when this component first transitioned to running. */
  started_at?: number | null
  /** Epoch seconds — when this component transitioned to done/error. */
  completed_at?: number | null
}

export interface ActiveAnalysisRun {
  run_id: string
  symbol: string
  started_at: number
  finished_at: number | null
  status: 'running' | 'success' | 'error' | 'timeout'
  stage_label: string
  active_component: FlowComponentKey | null
  error: string | null
  signal: string | null
  elapsed_seconds: number
  components: Record<FlowComponentKey, FlowComponentState>
}
