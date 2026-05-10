import { useState } from 'react'
import type { WatchlistEntry } from '../types'
import { triggerAnalysis, addToWatchlist, removeFromWatchlist } from '../api'

interface WatchlistPanelProps {
  entries: WatchlistEntry[]
  onRefresh: () => void
}

function SignalBadge({ signal }: { signal: string | null }) {
  if (!signal) return <span style={{ color: 'var(--text-secondary)' }}>—</span>

  const color = signal === 'BUY' ? 'var(--success-color)'
              : signal === 'SELL' ? 'var(--danger-color)'
              : 'var(--warning-color)'

  return (
    <span style={{
      display: 'inline-block',
      padding: '3px 10px',
      borderRadius: '12px',
      background: color,
      color: 'white',
      fontWeight: 700,
      fontSize: '0.8rem',
      letterSpacing: '0.05em',
    }}>
      {signal}
    </span>
  )
}

function ModeBadge({ mode }: { mode: string }) {
  const color = mode === 'commodity' ? '#f59e0b'
              : mode === 'forex' ? '#3b82f6'
              : '#6b7280'
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: '8px',
      background: color,
      color: 'white',
      fontSize: '0.72rem',
      fontWeight: 600,
      textTransform: 'uppercase',
    }}>
      {mode}
    </span>
  )
}

export function WatchlistPanel({ entries, onRefresh }: WatchlistPanelProps) {
  const [newSymbol, setNewSymbol] = useState('')
  const [triggering, setTriggering] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  async function handleTrigger(symbol: string) {
    setTriggering(symbol)
    try {
      await triggerAnalysis(symbol)
    } finally {
      setTriggering(null)
      setTimeout(onRefresh, 2000)
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!newSymbol.trim()) return
    setAdding(true)
    try {
      await addToWatchlist(newSymbol.trim().toUpperCase())
      setNewSymbol('')
      onRefresh()
    } finally {
      setAdding(false)
    }
  }

  async function handleRemove(symbol: string) {
    await removeFromWatchlist(symbol)
    onRefresh()
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div className="card-title" style={{ marginBottom: 0 }}>Watchlist — TradingView Monitored Symbols</div>
        <form onSubmit={handleAdd} style={{ display: 'flex', gap: '8px' }}>
          <input
            value={newSymbol}
            onChange={e => setNewSymbol(e.target.value.toUpperCase())}
            placeholder="Add symbol (e.g. GBPJPY)"
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid var(--border-color)',
              background: 'var(--primary-color)',
              color: 'var(--text-primary)',
              fontSize: '0.85rem',
              width: '180px',
            }}
          />
          <button
            type="submit"
            disabled={adding}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              border: 'none',
              background: 'var(--accent-color)',
              color: 'white',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.85rem',
            }}
          >
            {adding ? '…' : '+ Add'}
          </button>
        </form>
      </div>

      {entries.length === 0 ? (
        <div style={{ color: 'var(--text-secondary)', padding: '20px', textAlign: 'center' }}>
          No symbols in watchlist
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Type</th>
                <th>Data Source</th>
                <th>Analysts</th>
                <th>Interval</th>
                <th>Last Analysis</th>
                <th>Signal</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(entry => (
                <tr key={entry.symbol}>
                  <td>
                    <div>
                      <span className="symbol-badge">{entry.symbol}</span>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '3px' }}>
                        {entry.display_name}
                      </div>
                    </div>
                  </td>
                  <td><ModeBadge mode={entry.mode} /></td>
                  <td>
                    <span style={{
                      fontSize: '0.8rem',
                      color: entry.use_tradingview ? '#10b981' : 'var(--text-secondary)',
                      fontWeight: entry.use_tradingview ? 600 : 400,
                    }}>
                      {entry.use_tradingview ? '📊 TradingView' : 'yfinance'}
                    </span>
                  </td>
                  <td>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      {entry.analysts.join(', ')}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.85rem' }}>
                    {entry.interval_hours}h
                  </td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    {entry.last_analysis
                      ? new Date(entry.last_analysis).toLocaleString()
                      : <span style={{ color: 'var(--warning-color)' }}>Not yet</span>}
                  </td>
                  <td><SignalBadge signal={entry.last_signal} /></td>
                  <td>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button
                        onClick={() => handleTrigger(entry.symbol)}
                        disabled={triggering === entry.symbol}
                        title="Run analysis now"
                        style={{
                          padding: '4px 10px',
                          borderRadius: '5px',
                          border: 'none',
                          background: 'var(--accent-color)',
                          color: 'white',
                          cursor: 'pointer',
                          fontSize: '0.78rem',
                          fontWeight: 600,
                        }}
                      >
                        {triggering === entry.symbol ? '…' : '▶ Run'}
                      </button>
                      <button
                        onClick={() => handleRemove(entry.symbol)}
                        title="Remove from watchlist"
                        style={{
                          padding: '4px 8px',
                          borderRadius: '5px',
                          border: '1px solid var(--danger-color)',
                          background: 'transparent',
                          color: 'var(--danger-color)',
                          cursor: 'pointer',
                          fontSize: '0.78rem',
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
