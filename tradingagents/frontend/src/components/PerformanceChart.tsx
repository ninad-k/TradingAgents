import type { AccountStatus } from '../types'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface PerformanceChartProps {
  account: AccountStatus
}

const COLORS = ['#00c2e0', '#05e8a4']

export function PerformanceChart({ account }: PerformanceChartProps) {
  const data = [
    { name: 'Win Rate', value: account.win_rate },
    { name: 'Avg Duration (m)', value: Math.min(100, (account.avg_trade_duration || 0) / 60) },
  ]

  return (
    <div className="card">
      <div className="card-title">Performance Metrics</div>

      <div className="chart-container">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 12, right: 8, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey="name" stroke="var(--color-text-muted)" fontSize={12} />
            <YAxis stroke="var(--color-text-muted)" fontSize={12} />
            <Tooltip
              cursor={{ fill: 'rgba(0, 194, 224, 0.06)' }}
              contentStyle={{
                backgroundColor: 'var(--color-surface)',
                border: '1px solid var(--color-border-light)',
                borderRadius: 8,
                color: 'var(--color-text)',
                boxShadow: '0 8px 28px rgba(0,0,0,0.4)',
              }}
              labelStyle={{ color: 'var(--color-text-muted)' }}
            />
            <Bar dataKey="value" radius={[8, 8, 0, 0]}>
              {data.map((_, idx) => (
                <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
