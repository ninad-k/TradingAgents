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

  if (error) return <div className="card">Failed to load decisions: {error}</div>

  return (
    <div className="card">
      <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Decisions ({rows.length})</span>
        <div style={{ display: 'flex', gap: 10 }}>
          <input
            placeholder="filter symbol"
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value.toUpperCase())}
            style={{ width: 110 }}
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
        <div style={{ padding: 20, color: 'var(--text-secondary)' }}>No decisions yet.</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 12 }}>
          <thead>
            <tr style={{ textAlign: 'left', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              <th>id</th><th>decided_at</th><th>symbol</th><th>signal</th>
              <th>entry</th><th>exit</th><th>PnL %</th><th>evaluated</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const pnl = r.pnl_pct
              const pnlStyle = pnl == null
                ? {}
                : { color: pnl > 0 ? 'var(--success-color)' : pnl < 0 ? 'var(--danger-color)' : '' }
              return (
                <>
                  <tr
                    key={r.id}
                    onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                    style={{ borderTop: '1px solid var(--border)', cursor: 'pointer' }}
                  >
                    <td>{r.id}</td>
                    <td>{fmtTs(r.decided_at)}</td>
                    <td>{r.symbol}</td>
                    <td>{r.signal}</td>
                    <td>{fmtNum(r.entry_price, 5)}</td>
                    <td>{fmtNum(r.exit_price, 5)}</td>
                    <td style={pnlStyle}>{fmtNum(pnl, 2)}</td>
                    <td>{fmtTs(r.evaluated_at)}</td>
                  </tr>
                  {expanded === r.id && (
                    <tr key={`${r.id}-expanded`}>
                      <td colSpan={8} style={{ padding: 16, background: 'var(--bg-secondary)' }}>
                        <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Decision text</div>
                        <pre style={{ whiteSpace: 'pre-wrap', margin: '4px 0' }}>{r.decision_text || '—'}</pre>
                        {r.outcome_error && (
                          <div style={{ color: 'var(--danger-color)', fontSize: '0.85rem' }}>
                            Outcome error: {r.outcome_error}
                          </div>
                        )}
                        {r.params_snapshot && (
                          <details style={{ marginTop: 8 }}>
                            <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)' }}>
                              params_snapshot at decision time
                            </summary>
                            <pre style={{ margin: '4px 0' }}>{JSON.stringify(r.params_snapshot, null, 2)}</pre>
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
