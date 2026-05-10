/**API and component types */

export interface AccountStatus {
  trading_mode: string
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
}

export interface DashboardStatus {
  timestamp: string
  connected: boolean
  account: AccountStatus
  open_positions: Position[]
  recent_trades: Trade[]
  total_positions: number
  total_closed_trades: number
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
  mode: 'forex' | 'commodity' | 'stock'
  interval_hours: number
  analysts: string[]
  use_tradingview: boolean
  enabled: boolean
  last_analysis: string | null
  last_decision: string | null
  last_signal: string | null   // "BUY" | "SELL" | "HOLD" | null
  latest_result?: AnalysisResult
}

export interface AnalysisResult {
  symbol: string
  success: boolean
  signal: string
  decision_text: string
  error: string | null
  timestamp: string
}

export interface AnalysisEvent {
  type: string
  data: AnalysisResult
  timestamp: string
}
