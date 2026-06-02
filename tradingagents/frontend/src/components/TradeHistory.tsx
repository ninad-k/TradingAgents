import type { Trade } from '../types'

interface TradeHistoryProps {
  trades: Trade[]
}

export function TradeHistory({ trades }: TradeHistoryProps) {
  if (!trades || trades.length === 0) {
    return (
      <div>
        <div className="card-title">Trade History</div>
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
      <div className="card-title">Trade History (Last 20)</div>

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
            {trades.slice(0, 20).map((trade, idx) => {
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
