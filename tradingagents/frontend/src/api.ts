/**API client for dashboard backend */

import type { DashboardStatus } from './types'

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

export function subscribeToLiveUpdates(
  onUpdate: (status: DashboardStatus) => void,
  onError: (error: Event) => void
): WebSocket {
  const ws = new WebSocket('ws://localhost:8000/ws/live-updates')

  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      if (message.type === 'status_update' && message.data) {
        onUpdate(message.data as DashboardStatus)
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error)
    }
  }

  ws.onerror = onError

  return ws
}
