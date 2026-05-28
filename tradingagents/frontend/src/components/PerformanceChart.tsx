import type { AccountStatus } from '../types'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

interface PerformanceChartProps {
  account: AccountStatus
}

export function PerformanceChart({ account }: PerformanceChartProps) {
  // Sample data for demonstration
  const data = [
    { name: 'Win Rate', value: account.win_rate },
    { name: 'Avg Trade Duration (mins)', value: Math.min(100, (account.avg_trade_duration || 0) / 60) },
  ]

  return (
    <div className="card">
      <div className="card-title">Performance Metrics</div>

      <div className="chart-container">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis dataKey="name" stroke="var(--text-secondary)" />
            <YAxis stroke="var(--text-secondary)" />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--secondary-color)',
                border: `1px solid var(--border-color)`,
                color: 'var(--text-primary)'
              }}
            />
            <Bar dataKey="value" fill="var(--accent-color)" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
