/**API client for dashboard backend */

import type {
  DashboardStatus, WatchlistEntry, AnalysisEvent,
  Scoreboard, DecisionRow, Proposal, LearnedParams, Goals,
  AppSettings, SettingsResponse, BrokerSymbolsResponse, AnalysisResult,
  AnalysisJob, TriggerAnalysisResponse, AnalysisFlow, ActiveAnalysisRun,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
const WS_BASE = import.meta.env.VITE_WS_BASE ?? API_BASE.replace(/^http/, 'ws')

async function parseResponse<T>(response: Response, label: string): Promise<T> {
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload
      ? String(payload.detail)
      : `${label} failed (${response.status})`
    throw new Error(detail)
  }
  return payload as T
}

export async function getStatus(): Promise<DashboardStatus> {
  const response = await fetch(`${API_BASE}/api/status`)
  return response.json()
}

export async function getTrades(limit: number = 50): Promise<any[]> {
  const response = await fetch(`${API_BASE}/api/trades?limit=${limit}`)
  return response.json()
}

export async function getPortfolio(): Promise<any> {
  const response = await fetch(`${API_BASE}/api/portfolio`)
  return response.json()
}

export async function getAnalytics(): Promise<any> {
  const response = await fetch(`${API_BASE}/api/analytics`)
  return response.json()
}

export async function getBrokerSymbols(refresh: boolean = false): Promise<BrokerSymbolsResponse> {
  const qs = refresh ? '?refresh=true' : ''
  const response = await fetch(`${API_BASE}/api/symbols${qs}`)
  if (!response.ok) throw new Error(`broker symbols failed (${response.status})`)
  return response.json()
}

export async function getWatchlist(): Promise<WatchlistEntry[]> {
  const response = await fetch(`${API_BASE}/api/watchlist`)
  return response.json()
}

export async function triggerAnalysis(
  symbol: string,
  executeTrade: boolean = false,
  force: boolean = false,
): Promise<TriggerAnalysisResponse> {
  const qs = new URLSearchParams({
    execute_trade: String(executeTrade),
    force: String(force),
  })
  const response = await fetch(
    `${API_BASE}/api/watchlist/${symbol}/analyze?${qs.toString()}`,
    { method: 'POST' },
  )
  return parseResponse<TriggerAnalysisResponse>(response, 'trigger analysis')
}

export async function getAnalysisResult(symbol: string): Promise<AnalysisResult> {
  const response = await fetch(`${API_BASE}/api/watchlist/${symbol}/result`)
  return parseResponse<AnalysisResult>(response, 'analysis result')
}

export async function getAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const response = await fetch(`${API_BASE}/api/jobs/${jobId}`)
  return parseResponse<AnalysisJob>(response, 'analysis job')
}

/** Poll a job until it terminates (or our local deadline trips). */
export async function pollJobUntilDone(
  jobId: string,
  opts: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<AnalysisJob> {
  const interval = opts.intervalMs ?? 1500
  const timeout = opts.timeoutMs ?? 5 * 60_000
  const started = Date.now()
  while (true) {
    const job = await getAnalysisJob(jobId)
    if (['completed', 'failed', 'timeout'].includes(job.status)) return job
    if (Date.now() - started > timeout) {
      return { ...job, status: 'timeout', error: 'client poll timeout' }
    }
    await new Promise(r => setTimeout(r, interval))
  }
}

export async function getActiveAnalysisRuns(): Promise<ActiveAnalysisRun[]> {
  const response = await fetch(`${API_BASE}/api/analysis/active`)
  return parseResponse<ActiveAnalysisRun[]>(response, 'active analysis runs')
}

export async function getAnalysisFlows(opts: {
  limit?: number; symbol?: string;
} = {}): Promise<AnalysisFlow[]> {
  const params = new URLSearchParams()
  if (opts.limit != null) params.set('limit', String(opts.limit))
  if (opts.symbol) params.set('symbol', opts.symbol)
  const qs = params.toString()
  const response = await fetch(`${API_BASE}/api/analysis-flow${qs ? `?${qs}` : ''}`)
  return parseResponse<AnalysisFlow[]>(response, 'analysis flow')
}

export async function addToWatchlist(symbol: string, intervalMinutes: number = 1): Promise<any> {
  const response = await fetch(`${API_BASE}/api/watchlist/${symbol}?interval_minutes=${intervalMinutes}`, { method: 'POST' })
  return parseResponse<any>(response, 'add watchlist symbol')
}

export interface BulkAddResult {
  added: string[]
  failed: { symbol: string; error: string }[]
}

/** Fan-out N parallel adds to the single-symbol endpoint and aggregate the outcome. */
export async function addManyToWatchlist(
  symbols: string[],
  intervalMinutes: number = 1,
): Promise<BulkAddResult> {
  const unique = Array.from(new Set(
    symbols.map(s => s.trim().toUpperCase()).filter(Boolean)
  ))
  const settled = await Promise.allSettled(
    unique.map(s => addToWatchlist(s, intervalMinutes))
  )
  const added: string[] = []
  const failed: { symbol: string; error: string }[] = []
  settled.forEach((r, i) => {
    const symbol = unique[i]
    if (r.status === 'fulfilled') added.push(symbol)
    else failed.push({ symbol, error: String(r.reason ?? 'unknown error') })
  })
  return { added, failed }
}

export async function removeFromWatchlist(symbol: string): Promise<any> {
  const response = await fetch(`${API_BASE}/api/watchlist/${symbol}`, { method: 'DELETE' })
  return parseResponse<any>(response, 'remove watchlist symbol')
}

// ─── Learning loop ─────────────────────────────────────────────────────────

export async function getScoreboard(windowDays: number = 30): Promise<Scoreboard> {
  const response = await fetch(`${API_BASE}/api/learning/scoreboard?window_days=${windowDays}`)
  return response.json()
}

export async function getDecisions(opts: {
  limit?: number; symbol?: string; since?: string;
} = {}): Promise<DecisionRow[]> {
  const params = new URLSearchParams()
  if (opts.limit != null) params.set('limit', String(opts.limit))
  if (opts.symbol) params.set('symbol', opts.symbol)
  if (opts.since) params.set('since', opts.since)
  const qs = params.toString()
  const response = await fetch(`${API_BASE}/api/learning/decisions${qs ? `?${qs}` : ''}`)
  return response.json()
}

export async function getProposals(
  status: 'pending' | 'applied' | 'rejected' | 'all' = 'all',
  limit: number = 50,
): Promise<Proposal[]> {
  const response = await fetch(`${API_BASE}/api/learning/proposals?status=${status}&limit=${limit}`)
  return response.json()
}

export async function getProposal(id: number): Promise<Proposal> {
  const response = await fetch(`${API_BASE}/api/learning/proposals/${id}`)
  if (!response.ok) throw new Error(`proposal ${id} not found`)
  return response.json()
}

export async function approveProposal(id: number): Promise<{ applied: boolean; proposal_id: number; params: LearnedParams }> {
  const response = await fetch(`${API_BASE}/api/learning/proposals/${id}/approve`, { method: 'POST' })
  if (!response.ok) throw new Error(`approve failed (${response.status})`)
  return response.json()
}

export async function rejectProposal(id: number, reason?: string): Promise<any> {
  const response = await fetch(`${API_BASE}/api/learning/proposals/${id}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason ?? null }),
  })
  if (!response.ok) throw new Error(`reject failed (${response.status})`)
  return response.json()
}

export async function getLearnedParams(): Promise<LearnedParams> {
  const response = await fetch(`${API_BASE}/api/learning/params`)
  return response.json()
}

export async function getGoals(): Promise<Goals> {
  const response = await fetch(`${API_BASE}/api/learning/goals`)
  return response.json()
}

export async function getSettings(): Promise<SettingsResponse> {
  const response = await fetch(`${API_BASE}/api/settings`)
  if (!response.ok) throw new Error(`settings failed (${response.status})`)
  return response.json()
}

export async function updateSettings(settings: Partial<AppSettings>): Promise<SettingsResponse> {
  const response = await fetch(`${API_BASE}/api/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
  if (!response.ok) throw new Error(`settings update failed (${response.status})`)
  return response.json()
}

export function subscribeToLiveUpdates(
  onUpdate: (status: DashboardStatus, watchlist: WatchlistEntry[], events: AnalysisEvent[]) => void,
  onError: (error: Event) => void
): WebSocket {
  const ws = new WebSocket(`${WS_BASE}/ws/live-updates`)

  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      if (message.type === 'status_update' && message.data) {
        onUpdate(
          message.data as DashboardStatus,
          (message.watchlist || []) as WatchlistEntry[],
          (message.new_events || []) as AnalysisEvent[]
        )
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error)
    }
  }

  ws.onerror = onError
  return ws
}
