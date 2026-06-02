import type { Position } from '../types'

interface PortfolioSummaryProps {
  positions: Position[]
}

export function PortfolioSummary({ positions }: PortfolioSummaryProps) {
  if (!positions || positions.length === 0) {
    return (
      <div className="card">
        <div className="card-title">Open Positions</div>
        <div style={{
          color: 'var(--color-text-muted)',
          textAlign: 'center',
          padding: 28,
          fontSize: '0.9rem',
        }}>
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
              <th>P&amp;L</th>
              <th>Comment</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => {
              const isLong = pos.direction.toLowerCase() === 'long' || pos.direction.toLowerCase() === 'buy'
              const dirColor = isLong ? 'var(--color-profit)' : 'var(--color-loss)'
              return (
                <tr key={pos.symbol}>
                  <td><span className="symbol-badge">{pos.symbol}</span></td>
                  <td style={{
                    textTransform: 'uppercase',
                    color: dirColor,
                    fontWeight: 700,
                    letterSpacing: '0.04em',
                    fontSize: '0.78rem',
                  }}>
                    {pos.direction}
                  </td>
                  <td>{pos.quantity}</td>
                  <td>${pos.entry_price.toFixed(2)}</td>
                  <td>${pos.current_price.toFixed(2)}</td>
                  <td style={{
                    color: pos.unrealized_pnl >= 0 ? 'var(--color-profit)' : 'var(--color-loss)',
                    fontWeight: 700,
                  }}>
                    ${pos.unrealized_pnl.toFixed(2)} ({pos.unrealized_pnl_percent >= 0 ? '+' : ''}{pos.unrealized_pnl_percent.toFixed(2)}%)
                  </td>
                  <td style={{ color: 'var(--color-text-muted)' }}>{pos.comment || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
