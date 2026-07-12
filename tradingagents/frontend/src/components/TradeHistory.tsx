import { useState, useEffect, useRef } from 'react'
import type { Trade } from '../types'
import { getTrades } from '../api'

const REFRESH_MS = 15_000

export function TradeHistory() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true

    const load = async () => {
      try {
        const data = await getTrades(20) as Trade[]
        if (!mountedRef.current) return
        setTrades(data)
        setLastUpdated(new Date())
      } catch {
        // background refresh — silently skip
      }
    }

    load()
    const id = window.setInterval(load, REFRESH_MS)
    return () => {
      mountedRef.current = false
      window.clearInterval(id)
    }
  }, [])

  if (trades.length === 0) {
    return (
      <div>
        <div className="card-title">Trade History (Last 20)</div>
        <div style={{
          color: 'var(--color-text-muted)',
          textAlign: 'center',
          padding: 28,
          fontSize: '0.9rem',
        }}>
          No trades yet
        </div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div className="card-title" style={{ margin: 0 }}>Trade History (Last 20)</div>
        {lastUpdated && (
          <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
            Updated {lastUpdated.toLocaleTimeString()}
          </span>
        )}
      </div>

      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Direction</th>
              <th>Entry Price</th>
              <th>Entry Time</th>
              <th>Exit Price</th>
              <th>P&amp;L</th>
              <th>Status</th>
              <th>Comment</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade, idx) => {
              const isLong = trade.direction.toLowerCase() === 'long' || trade.direction.toLowerCase() === 'buy'
              const dirColor = isLong ? 'var(--color-profit)' : 'var(--color-loss)'
              return (
                <tr key={idx}>
                  <td><span className="symbol-badge">{trade.symbol}</span></td>
                  <td style={{
                    textTransform: 'uppercase',
                    color: dirColor,
                    fontWeight: 700,
                    letterSpacing: '0.04em',
                    fontSize: '0.78rem',
                  }}>
                    {trade.direction}
                  </td>
                  <td>${trade.entry_price.toFixed(2)}</td>
                  <td style={{ color: 'var(--color-text-dim)' }}>
                    {new Date(trade.entry_time).toLocaleString()}
                  </td>
                  <td>{trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : '—'}</td>
                  <td style={{
                    color: trade.pnl && trade.pnl >= 0 ? 'var(--color-profit)' : 'var(--color-loss)',
                    fontWeight: 700,
                  }}>
                    {trade.pnl ? `$${trade.pnl.toFixed(2)}` : '—'}
                  </td>
                  <td>
                    <span className={`action-badge ${trade.status}`}>
                      {trade.status}
                    </span>
                  </td>
                  <td style={{ color: 'var(--color-text-muted)' }}>
                    {trade.comment || trade.reason || '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
