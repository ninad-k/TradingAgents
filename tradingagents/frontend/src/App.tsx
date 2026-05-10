import { useState, useEffect } from 'react'
import type { DashboardStatus } from './types'
import { subscribeToLiveUpdates, getStatus } from './api'
import { Dashboard } from './components/Dashboard'
import './App.css'

function App() {
  const [status, setStatus] = useState<DashboardStatus | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Initial status fetch
    getStatus()
      .then(setStatus)
      .catch((err) => {
        console.error('Failed to fetch initial status:', err)
        setError('Failed to connect to trading dashboard API')
      })

    // WebSocket subscription for live updates
    let ws: WebSocket | null = null

    try {
      ws = subscribeToLiveUpdates(
        (newStatus) => {
          setStatus(newStatus)
          setConnected(true)
          setError(null)
        },
        (err) => {
          console.error('WebSocket error:', err)
          setConnected(false)
        }
      )
    } catch (err) {
      console.error('Failed to establish WebSocket connection:', err)
      setError('Failed to establish real-time connection')
    }

    return () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
    }
  }, [])

  return (
    <div className="app">
      <div className="header">
        <div>
          <h1>📈 Trading Dashboard</h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: '5px' }}>
            Real-time trading activity and performance monitoring
          </p>
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
        <Dashboard status={status} />
      ) : (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>
          Loading dashboard...
        </div>
      )}
    </div>
  )
}

export default App
