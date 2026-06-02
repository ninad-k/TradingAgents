import type { AccountStatus } from '../types'

interface AccountOverviewProps {
  account: AccountStatus
}

const stat = {
  label: {
    color: 'var(--color-text-muted)',
    fontSize: '0.78rem',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.08em',
    marginBottom: 6,
    fontWeight: 600,
  },
  value: {
    fontSize: '1.45rem',
    fontWeight: 700,
    color: 'var(--color-text)',
    letterSpacing: '-0.01em',
    fontVariantNumeric: 'tabular-nums' as const,
  },
}

export function AccountOverview({ account }: AccountOverviewProps) {
  return (
    <div>
      <div className="card-title">Account Overview</div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        <div>
          <div style={stat.label}>Account Balance</div>
          <div style={stat.value}>${account.account_balance.toFixed(2)}</div>
        </div>

        <div>
          <div style={stat.label}>Available Margin</div>
          <div style={stat.value}>${account.available_margin.toFixed(2)}</div>
        </div>

        <div>
          <div style={stat.label}>Largest Win</div>
          <div style={{ ...stat.value, color: 'var(--color-profit)' }}>
            ${account.largest_win.toFixed(2)}
          </div>
        </div>

        <div>
          <div style={stat.label}>Largest Loss</div>
          <div style={{ ...stat.value, color: 'var(--color-loss)' }}>
            ${account.largest_loss.toFixed(2)}
          </div>
        </div>
      </div>

      <div style={{
        marginTop: 22,
        paddingTop: 18,
        borderTop: '1px solid var(--color-border)',
      }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
          <div>
            <div style={stat.label}>Total Trades</div>
            <div style={{ ...stat.value, fontSize: '1.2rem' }}>{account.total_trades}</div>
          </div>
          <div>
            <div style={stat.label}>Closed Trades</div>
            <div style={{ ...stat.value, fontSize: '1.2rem' }}>{account.closed_trades}</div>
          </div>
        </div>
      </div>
    </div>
  )
}
