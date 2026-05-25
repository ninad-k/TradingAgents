/**API client for dashboard backend */

import type {
  DashboardStatus, WatchlistEntry, AnalysisEvent,
  Scoreboard, DecisionRow, Proposal, LearnedParams, Goals,
} from './types'

const API_BASE = 'http://localhost:8000'

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

export async function getWatchlist(): Promise<WatchlistEntry[]> {
  const response = await fetch(`${API_BASE}/api/watchlist`)
  return response.json()
}

export async function triggerAnalysis(symbol: string): Promise<any> {
  const response = await fetch(`${API_BASE}/api/watchlist/${symbol}/analyze`, { method: 'POST' })
  return response.json()
}

export async function addToWatchlist(symbol: string, intervalHours: number = 4): Promise<any> {
  const response = await fetch(`${API_BASE}/api/watchlist/${symbol}?interval_hours=${intervalHours}`, { method: 'POST' })
  return response.json()
}

export async function removeFromWatchlist(symbol: string): Promise<any> {
  const response = await fetch(`${API_BASE}/api/watchlist/${symbol}`, { method: 'DELETE' })
  return response.json()
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

export function subscribeToLiveUpdates(
  onUpdate: (status: DashboardStatus, watchlist: WatchlistEntry[], events: AnalysisEvent[]) => void,
  onError: (error: Event) => void
): WebSocket {
  const ws = new WebSocket('ws://localhost:8000/ws/live-updates')

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
