import { useState, useEffect, useCallback } from 'react'
import type { DashboardStatus, WatchlistEntry, AnalysisEvent } from './types'
import { subscribeToLiveUpdates, getStatus, getWatchlist } from './api'
import { Dashboard } from './components/Dashboard'
import './App.css'

function App() {
  const [status, setStatus] = useState<DashboardStatus | null>(null)
  const [watchlistEntries, setWatchlistEntries] = useState<WatchlistEntry[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshWatchlist = useCallback(() => {
    getWatchlist().then(setWatchlistEntries).catch(console.error)
  }, [])

  useEffect(() => {
    getStatus()
      .then(setStatus)
      .catch(() => setError('Failed to connect to trading dashboard API'))

    getWatchlist()
      .then(setWatchlistEntries)
      .catch(console.error)

    let ws: WebSocket | null = null
    try {
      ws = subscribeToLiveUpdates(
        (newStatus: DashboardStatus, wl: WatchlistEntry[], _events: AnalysisEvent[]) => {
          setStatus(newStatus)
          if (wl && wl.length > 0) setWatchlistEntries(wl)
          setConnected(true)
          setError(null)
        },
        () => setConnected(false)
      )
    } catch {
      setError('Failed to establish real-time connection')
    }

    return () => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.close()
    }
  }, [])

  return (
    <div className="app">
      <div className="header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <img src="/favicon.svg" alt="ReyHedgeFund" style={{ width: '44px', height: '44px' }} />
            <div>
              <h1 style={{ margin: 0 }}>ReyHedgeFund</h1>
              <p style={{ color: 'var(--text-secondary)', marginTop: '3px', fontSize: '0.85rem' }}>
                Smart Investments · Real-time Trading Dashboard
              </p>
            </div>
          </div>
        </div>
        <div className="status-indicator">
          <div className={`status-dot ${connected ? 'connected' : 'disconnected'}`}></div>
          <span>{connected ? 'Live' : 'Connecting...'}</span>
          {status && (
            <span className={`trading-mode-badge ${status.account.trading_mode.toLowerCase()}`}>
              {status.account.trading_mode.toUpperCase()}
            </span>
          )}
        </div>
      </div>

      {error && (
        <div style={{
          padding: '15px',
          backgroundColor: 'var(--danger-color)',
          borderRadius: '8px',
          marginBottom: '20px',
          color: 'white'
        }}>
          ⚠️ {error}
        </div>
      )}

      {status ? (
        <Dashboard status={status} watchlistEntries={watchlistEntries} onWatchlistRefresh={refreshWatchlist} />
      ) : (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
          Loading dashboard...
        </div>
      )}
    </div>
  )
}

export default App
