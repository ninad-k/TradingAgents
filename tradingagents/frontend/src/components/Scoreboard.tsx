import { useEffect, useState } from 'react'
import type { DecisionRow, Scoreboard } from '../types'
import { getDecisions, getScoreboard } from '../api'

const fmt = (v: number | null | undefined, digits = 3) =>
  v == null || Number.isNaN(v) ? '—' : v.toFixed(digits)
const fmtPct = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(1)}%`

export function ScoreboardPanel() {
  const [windowDays, setWindowDays] = useState(30)
  const [sb, setSb] = useState<Scoreboard | null>(null)
  const [decisions, setDecisions] = useState<DecisionRow[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    Promise.all([
      getScoreboard(windowDays),
      getDecisions({ limit: 8 }),
    ])
      .then(([scoreboard, rows]) => {
        setSb(scoreboard)
        setDecisions(rows)
      })
      .catch((e) => setError(String(e)))
  }, [windowDays])

  if (error) return (
    <div className="card alert-banner" style={{ margin: 0 }}>
      ⚠️ Couldn't reach the scoreboard. Retrying — keep this tab open.
    </div>
  )
  if (!sb) return (
    <div className="card">
      <div className="skeleton skeleton-line sm" />
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: 20,
        marginTop: 14,
      }}>
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
          <div key={i} style={{ padding: 14, background: 'var(--color-surface-2)', borderRadius: 'var(--radius-sm)' }}>
            <div className="skeleton skeleton-line sm" />
            <div className="skeleton skeleton-line lg" style={{ marginTop: 6 }} />
          </div>
        ))}
      </div>
    </div>
  )

  const signColor = (v: number | null | undefined) =>
    v == null ? '' : v > 0 ? 'var(--color-profit)' : v < 0 ? 'var(--color-loss)' : ''

  return (
    <div className="card">
      <div className="card-title" style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span>Scoreboard</span>
        <label style={{
          fontSize: '0.78rem',
          color: 'var(--color-text-muted)',
          textTransform: 'none',
          letterSpacing: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          Window:
          <select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))}>
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
        </label>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: 20,
        marginTop: 12,
      }}>
        <Stat label="Decisions" value={sb.n_decisions.toString()} />
        <Stat label="Evaluated" value={sb.n_evaluated.toString()} />
        <Stat label="Win rate" value={fmtPct(sb.win_rate)} />
        <Stat label="Mean PnL %" value={fmt(sb.mean_pnl_pct, 2)} color={signColor(sb.mean_pnl_pct)} />
        <Stat label="Stdev PnL %" value={fmt(sb.stdev_pnl_pct, 2)} />
        <Stat label="Sharpe" value={fmt(sb.sharpe, 2)} />
        <Stat label="Max DD %" value={fmt(sb.max_drawdown_pct, 2)} color={signColor(sb.max_drawdown_pct)} />
        <Stat label="Total return %" value={fmt(sb.total_return_pct, 2)} color={signColor(sb.total_return_pct)} />
      </div>

      {sb.n_evaluated === 0 && (
        <div style={{
          marginTop: 22,
          padding: '14px 16px',
          borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--color-border)',
          background: 'var(--color-warning-dim)',
          color: 'var(--color-warning)',
          fontSize: '0.86rem',
          lineHeight: 1.5,
        }}>
          No evaluated outcomes yet. Scoreboard performance metrics populate after a successful decision has an
          entry price, exit price, and PnL outcome. Current logged decisions are failed or still unevaluated.
        </div>
      )}

      {Object.keys(sb.per_signal).length > 0 && (
        <div style={{ marginTop: 28 }}>
          <div style={{
            fontSize: '0.78rem',
            color: 'var(--color-text-muted)',
            marginBottom: 10,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontWeight: 600,
          }}>
            By signal
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Signal</th><th>Count</th><th>Win rate</th><th>Mean PnL %</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(sb.per_signal).map(([sig, s]) => (
                <tr key={sig}>
                  <td><span className="symbol-badge">{sig}</span></td>
                  <td>{s.count}</td>
                  <td>{fmtPct(s.win_rate)}</td>
                  <td style={{
                    color: signColor(s.mean_pnl_pct),
                    fontWeight: 600,
                  }}>
                    {fmt(s.mean_pnl_pct, 2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {decisions.length > 0 && (
        <div style={{ marginTop: 28 }}>
          <div style={{
            fontSize: '0.78rem',
            color: 'var(--color-text-muted)',
            marginBottom: 10,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontWeight: 600,
          }}>
            Recent decisions
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Signal</th>
                <th>Status</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((row) => (
                <tr key={row.id}>
                  <td style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>
                    {new Date(row.decided_at).toLocaleString()}
                  </td>
                  <td><span className="symbol-badge">{row.symbol}</span></td>
                  <td>{row.signal === 'UNKNOWN' ? '-' : row.signal}</td>
                  <td style={{ color: row.success ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                    {row.success ? 'Success' : 'Failed'}
                  </td>
                  <td
                    title={row.outcome_error || row.error || undefined}
                    style={{
                      maxWidth: 460,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      color: row.pnl_pct == null ? 'var(--color-text-muted)' : signColor(row.pnl_pct),
                    }}
                  >
                    {row.pnl_pct != null
                      ? `${(row.pnl_pct * 100).toFixed(2)}%`
                      : row.error || row.outcome_error || 'Pending evaluation'}
                  </td>
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
    <div style={{
      padding: '14px 16px',
      background: 'var(--color-surface-2)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-sm)',
    }}>
      <div style={{
        color: 'var(--color-text-muted)',
        fontSize: '0.7rem',
        marginBottom: 6,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        fontWeight: 600,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: '1.4rem',
        fontWeight: 700,
        color: color || 'var(--color-text)',
        fontVariantNumeric: 'tabular-nums',
        letterSpacing: '-0.01em',
      }}>
        {value}
      </div>
    </div>
  )
}
