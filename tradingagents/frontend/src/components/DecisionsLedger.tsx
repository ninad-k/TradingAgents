import { useEffect, useState } from 'react'
import type { DecisionRow } from '../types'
import { getDecisions } from '../api'

const fmtTs = (v?: string | null) => {
  if (!v) return '—'
  try { return new Date(v).toLocaleString() } catch { return v }
}
const fmtNum = (v: number | null | undefined, digits: number = 4) =>
  v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(digits)

export function DecisionsLedger() {
  const [rows, setRows] = useState<DecisionRow[]>([])
  const [expanded, setExpanded] = useState<number | null>(null)
  const [symbolFilter, setSymbolFilter] = useState('')
  const [limit, setLimit] = useState(50)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    getDecisions({ symbol: symbolFilter || undefined, limit })
      .then(setRows)
      .catch((e) => setError(String(e)))
  }, [symbolFilter, limit])

  if (error) return (
    <div className="card alert-banner" style={{ margin: 0 }}>
      ⚠️ Couldn't load decisions. Retrying — keep this tab open.
    </div>
  )

  return (
    <div className="card">
      <div className="card-title" style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span>Decisions ({rows.length})</span>
        <div style={{ display: 'flex', gap: 10 }}>
          <input
            placeholder="filter symbol"
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value.toUpperCase())}
            style={{ width: 130 }}
          />
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>
        </div>
      </div>

      {rows.length === 0 ? (
        <div style={{ padding: 24, color: 'var(--color-text-muted)' }}>
          No decisions yet.
        </div>
      ) : (
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th>ID</th><th>Decided at</th><th>Symbol</th><th>Signal</th>
              <th>Entry</th><th>Exit</th><th>PnL %</th><th>Evaluated</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const pnl = r.pnl_pct
              const pnlStyle = pnl == null
                ? {}
                : {
                  color: pnl > 0
                    ? 'var(--color-profit)'
                    : pnl < 0
                    ? 'var(--color-loss)'
                    : '',
                  fontWeight: 700,
                }
              return (
                <>
                  <tr
                    key={r.id}
                    onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ color: 'var(--color-text-muted)' }}>{r.id}</td>
                    <td style={{ color: 'var(--color-text-dim)' }}>{fmtTs(r.decided_at)}</td>
                    <td><span className="symbol-badge">{r.symbol}</span></td>
                    <td>
                      <span style={{
                        fontWeight: 700,
                        color:
                          r.signal === 'BUY' ? 'var(--color-profit)' :
                          r.signal === 'SELL' ? 'var(--color-loss)' :
                          'var(--color-warning)',
                      }}>
                        {r.signal}
                      </span>
                    </td>
                    <td>{fmtNum(r.entry_price, 5)}</td>
                    <td>{fmtNum(r.exit_price, 5)}</td>
                    <td style={pnlStyle}>{fmtNum(pnl, 2)}</td>
                    <td style={{ color: 'var(--color-text-dim)' }}>{fmtTs(r.evaluated_at)}</td>
                  </tr>
                  {expanded === r.id && (
                    <tr key={`${r.id}-expanded`}>
                      <td colSpan={8} style={{
                        padding: 18,
                        background: 'var(--color-surface-2)',
                        borderTop: '1px solid var(--color-border-light)',
                      }}>
                        <div style={{
                          fontSize: '0.78rem',
                          color: 'var(--color-text-muted)',
                          textTransform: 'uppercase',
                          letterSpacing: '0.08em',
                          fontWeight: 600,
                          marginBottom: 4,
                        }}>
                          Decision text
                        </div>
                        <pre style={{
                          whiteSpace: 'pre-wrap',
                          margin: '4px 0',
                          fontFamily: 'inherit',
                          color: 'var(--color-text)',
                        }}>
                          {r.decision_text || '—'}
                        </pre>
                        {r.outcome_error && (
                          <div style={{
                            color: 'var(--color-loss)',
                            fontSize: '0.85rem',
                            marginTop: 8,
                          }}>
                            Outcome error: {r.outcome_error}
                          </div>
                        )}
                        {r.params_snapshot && (
                          <details style={{ marginTop: 10 }}>
                            <summary style={{
                              cursor: 'pointer',
                              color: 'var(--color-primary)',
                              fontSize: '0.85rem',
                            }}>
                              params_snapshot at decision time
                            </summary>
                            <pre style={{
                              margin: '8px 0',
                              padding: 12,
                              background: 'var(--color-background)',
                              border: '1px solid var(--color-border)',
                              borderRadius: 6,
                              fontSize: '0.82rem',
                              color: 'var(--color-text-dim)',
                            }}>
                              {JSON.stringify(r.params_snapshot, null, 2)}
                            </pre>
                          </details>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
