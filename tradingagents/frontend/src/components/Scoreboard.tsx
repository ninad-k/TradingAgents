import { useEffect, useState } from 'react'
import type { Scoreboard } from '../types'
import { getScoreboard } from '../api'

const fmt = (v: number | null | undefined, digits = 3) =>
  v == null || Number.isNaN(v) ? '—' : v.toFixed(digits)
const fmtPct = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(1)}%`

export function ScoreboardPanel() {
  const [windowDays, setWindowDays] = useState(30)
  const [sb, setSb] = useState<Scoreboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    getScoreboard(windowDays)
      .then(setSb)
      .catch((e) => setError(String(e)))
  }, [windowDays])

  if (error) return <div className="card">Failed to load scoreboard: {error}</div>
  if (!sb) return <div className="card">Loading scoreboard…</div>

  const signColor = (v: number | null | undefined) =>
    v == null ? '' : v > 0 ? 'var(--success-color)' : v < 0 ? 'var(--danger-color)' : ''

  return (
    <div className="card">
      <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Scoreboard</span>
        <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
          Window:&nbsp;
          <select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))}>
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
        </label>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginTop: 12 }}>
        <Stat label="Decisions" value={sb.n_decisions.toString()} />
        <Stat label="Evaluated" value={sb.n_evaluated.toString()} />
        <Stat label="Win rate" value={fmtPct(sb.win_rate)} />
        <Stat label="Mean PnL %" value={fmt(sb.mean_pnl_pct, 2)} color={signColor(sb.mean_pnl_pct)} />
        <Stat label="Stdev PnL %" value={fmt(sb.stdev_pnl_pct, 2)} />
        <Stat label="Sharpe" value={fmt(sb.sharpe, 2)} />
        <Stat label="Max DD %" value={fmt(sb.max_drawdown_pct, 2)} color={signColor(sb.max_drawdown_pct)} />
        <Stat label="Total return %" value={fmt(sb.total_return_pct, 2)} color={signColor(sb.total_return_pct)} />
      </div>

      {Object.keys(sb.per_signal).length > 0 && (
        <div style={{ marginTop: 24 }}>
          <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: 8 }}>
            By signal
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                <th>Signal</th><th>Count</th><th>Win rate</th><th>Mean PnL %</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(sb.per_signal).map(([sig, s]) => (
                <tr key={sig} style={{ borderTop: '1px solid var(--border)' }}>
                  <td>{sig}</td>
                  <td>{s.count}</td>
                  <td>{fmtPct(s.win_rate)}</td>
                  <td style={{ color: signColor(s.mean_pnl_pct) }}>{fmt(s.mean_pnl_pct, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: 5 }}>{label}</div>
      <div style={{ fontSize: '1.4rem', fontWeight: 'bold', color: color || undefined }}>{value}</div>
    </div>
  )
}
