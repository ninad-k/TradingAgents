import type { DashboardStatus } from '../types'
import { MetricsCards } from './MetricsCards'
import { AccountOverview } from './AccountOverview'
import { PortfolioSummary } from './PortfolioSummary'
import { TradeHistory } from './TradeHistory'
import { PerformanceChart } from './PerformanceChart'

interface DashboardProps {
  status: DashboardStatus
}

export function Dashboard({ status }: DashboardProps) {
  return (
    <div>
      {/* Key Metrics Row */}
      <MetricsCards account={status.account} />

      {/* Main Dashboard Grid */}
      <div className="container">
        <div className="card grid-2col">
          <AccountOverview account={status.account} />
        </div>

        <PortfolioSummary positions={status.open_positions} />

        <PerformanceChart account={status.account} />
      </div>

      {/* Trade History */}
      <div className="card">
        <TradeHistory trades={status.recent_trades} />
      </div>
    </div>
  )
}
