/**API client for dashboard backend */

import type { DashboardStatus, WatchlistEntry, AnalysisEvent } from './types'

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
