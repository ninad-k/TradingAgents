import type { Trade } from '../types'

interface TradeHistoryProps {
  trades: Trade[]
}

export function TradeHistory({ trades }: TradeHistoryProps) {
  if (!trades || trades.length === 0) {
    return (
      <div>
        <div className="card-title">Trade History</div>
        <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '20px' }}>
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
              <th>P&L</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice(0, 20).map((trade, idx) => (
              <tr key={idx}>
                <td>
                  <span className="symbol-badge">{trade.symbol}</span>
                </td>
                <td style={{ textTransform: 'uppercase' }}>{trade.direction}</td>
                <td>${trade.entry_price.toFixed(2)}</td>
                <td>{new Date(trade.entry_time).toLocaleString()}</td>
                <td>{trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : '-'}</td>
                <td style={{
                  color: trade.pnl && trade.pnl >= 0 ? 'var(--success-color)' : 'var(--danger-color)',
                  fontWeight: 'bold'
                }}>
                  {trade.pnl ? `$${trade.pnl.toFixed(2)}` : '-'}
                </td>
                <td>
                  <span className={`action-badge ${trade.status}`}>
                    {trade.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
