import type { AccountStatus } from '../types'

interface AccountOverviewProps {
  account: AccountStatus
}

export function AccountOverview({ account }: AccountOverviewProps) {
  return (
    <div>
      <div className="card-title">Account Overview</div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        <div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '5px' }}>
            Account Balance
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
            ${account.account_balance.toFixed(2)}
          </div>
        </div>

        <div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '5px' }}>
            Available Margin
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
            ${account.available_margin.toFixed(2)}
          </div>
        </div>

        <div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '5px' }}>
            Largest Win
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--success-color)' }}>
            ${account.largest_win.toFixed(2)}
          </div>
        </div>

        <div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '5px' }}>
            Largest Loss
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--danger-color)' }}>
            ${account.largest_loss.toFixed(2)}
          </div>
        </div>
      </div>

      <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px solid var(--border-color)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
          <div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Total Trades</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 'bold' }}>{account.total_trades}</div>
          </div>
          <div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Closed Trades</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 'bold' }}>{account.closed_trades}</div>
          </div>
        </div>
      </div>
    </div>
  )
}
