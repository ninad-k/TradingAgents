import { useEffect, useState } from 'react'
import type { Goals, LearnedParams } from '../types'
import { getGoals, getLearnedParams } from '../api'

export function LearnedParamsPanel() {
  const [params, setParams] = useState<LearnedParams | null>(null)
  const [goals, setGoals] = useState<Goals | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    Promise.all([getLearnedParams(), getGoals()])
      .then(([p, g]) => { setParams(p); setGoals(g) })
      .catch((e) => setError(String(e)))
  }, [])

  if (error) return <div className="card">Failed to load params: {error}</div>
  if (!params || !goals) return <div className="card">Loading params…</div>

  return (
    <div className="card">
      <div className="card-title">Learned params &amp; goals</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 12 }}>
        <div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: 6 }}>
            learned_params.json (mutable)
          </div>
          <KVTable obj={params} />
        </div>
        <div>
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: 6 }}>
            goals.json (read-only targets)
          </div>
          <KVTable obj={goals} />
        </div>
      </div>
    </div>
  )
}

function KVTable({ obj }: { obj: Record<string, unknown> }) {
  const entries = Object.entries(obj)
  if (entries.length === 0) {
    return <div style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>(empty)</div>
  }
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} style={{ borderTop: '1px solid var(--border)' }}>
            <td style={{ padding: '6px 8px', color: 'var(--text-secondary)' }}>{k}</td>
            <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: 'monospace' }}>
              {typeof v === 'object' ? JSON.stringify(v) : String(v)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
