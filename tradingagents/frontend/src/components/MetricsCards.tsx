import type { AccountStatus } from '../types'

interface MetricsCardsProps {
  account: AccountStatus
}

export function MetricsCards({ account }: MetricsCardsProps) {
  const metrics = [
    {
      title: 'Account Balance',
      value: `$${account.account_balance.toFixed(2)}`,
      subtext: `Equity: $${account.account_equity.toFixed(2)}`,
      variant: 'card card-primary',
    },
    {
      title: 'Total P&L',
      value: `$${account.total_pnl.toFixed(2)}`,
      subtext: `${account.total_pnl_percent >= 0 ? '+' : ''}${account.total_pnl_percent.toFixed(2)}%`,
      color: account.total_pnl >= 0 ? 'metric-positive' : 'metric-negative',
      variant: 'card',
    },
    {
      title: 'Win Rate',
      value: `${account.win_rate.toFixed(1)}%`,
      subtext: `${account.total_trades} total trades`,
      variant: 'card',
    },
    {
      title: 'Open Trades',
      value: account.open_trades.toString(),
      subtext: `Closed: ${account.closed_trades}`,
      variant: 'card card-gold',
    },
  ]

  return (
    <div className="container" style={{ marginBottom: 24 }}>
      {metrics.map((metric) => (
        <div key={metric.title} className={metric.variant}>
          <div className="card-title">{metric.title}</div>
          <div className={`card-value ${metric.color || ''}`}>{metric.value}</div>
          <div className="card-subtext">{metric.subtext}</div>
        </div>
      ))}
    </div>
  )
}
