import type { Position } from '../types'

interface PortfolioSummaryProps {
  positions: Position[]
}

export function PortfolioSummary({ positions }: PortfolioSummaryProps) {
  if (!positions || positions.length === 0) {
    return (
      <div className="card">
        <div className="card-title">Open Positions</div>
        <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '20px' }}>
          No open positions
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card-title">Open Positions ({positions.length})</div>

      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Direction</th>
              <th>Quantity</th>
              <th>Entry Price</th>
              <th>Current Price</th>
              <th>P&L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => (
              <tr key={pos.symbol}>
                <td>
                  <span className="symbol-badge">{pos.symbol}</span>
                </td>
                <td style={{ textTransform: 'uppercase' }}>{pos.direction}</td>
                <td>{pos.quantity}</td>
                <td>${pos.entry_price.toFixed(2)}</td>
                <td>${pos.current_price.toFixed(2)}</td>
                <td style={{
                  color: pos.unrealized_pnl >= 0 ? 'var(--success-color)' : 'var(--danger-color)',
                  fontWeight: 'bold'
                }}>
                  ${pos.unrealized_pnl.toFixed(2)} ({pos.unrealized_pnl_percent >= 0 ? '+' : ''}{pos.unrealized_pnl_percent.toFixed(2)}%)
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
