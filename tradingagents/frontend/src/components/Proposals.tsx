import { useEffect, useState } from 'react'
import type { Proposal } from '../types'
import { approveProposal, getProposals, rejectProposal } from '../api'

type Filter = 'pending' | 'applied' | 'rejected' | 'all'

const fmtTs = (v?: string | null) => {
  if (!v) return '—'
  try { return new Date(v).toLocaleString() } catch { return v }
}

export function ProposalsPanel() {
  const [filter, setFilter] = useState<Filter>('pending')
  const [rows, setRows] = useState<Proposal[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [refreshTick, setRefreshTick] = useState(0)

  useEffect(() => {
    setError(null)
    getProposals(filter, 50).then(setRows).catch((e) => setError(String(e)))
  }, [filter, refreshTick])

  const onApprove = async (id: number) => {
    if (!window.confirm(`Apply proposal #${id}? This rewrites learned_params.json.`)) return
    setBusyId(id)
    try {
      await approveProposal(id)
      setRefreshTick((t) => t + 1)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusyId(null)
    }
  }

  const onReject = async (id: number) => {
    const reason = window.prompt(`Reject proposal #${id} — reason (optional):`) ?? undefined
    setBusyId(id)
    try {
      await rejectProposal(id, reason || undefined)
      setRefreshTick((t) => t + 1)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="card">
      <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Proposals</span>
        <select value={filter} onChange={(e) => setFilter(e.target.value as Filter)}>
          <option value="pending">Pending</option>
          <option value="applied">Applied</option>
          <option value="rejected">Rejected</option>
          <option value="all">All</option>
        </select>
      </div>

      {error && (
        <div style={{ color: 'var(--danger-color)', padding: 10 }}>⚠️ {error}</div>
      )}

      {rows.length === 0 ? (
        <div style={{ padding: 20, color: 'var(--text-secondary)' }}>No {filter} proposals.</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 12 }}>
          <thead>
            <tr style={{ textAlign: 'left', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              <th>id</th><th>proposed_at</th><th>change</th><th>rationale</th><th>status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const key = p.diff ? Object.keys(p.diff)[0] : null
              const change = key
                ? `${key}: ${String(p.diff![key].from)} → ${String(p.diff![key].to)}`
                : '—'
              const status = p.applied
                ? <span style={{ color: 'var(--success-color)' }}>applied {fmtTs(p.applied_at)}</span>
                : p.rejected_at
                ? <span style={{ color: 'var(--danger-color)' }}>rejected {fmtTs(p.rejected_at)}</span>
                : <span style={{ color: 'var(--warning-color, #c2a000)' }}>pending</span>
              const showActions = !p.applied && !p.rejected_at
              return (
                <tr key={p.id} style={{ borderTop: '1px solid var(--border)' }}>
                  <td>{p.id}</td>
                  <td>{fmtTs(p.proposed_at)}</td>
                  <td><code>{change}</code></td>
                  <td style={{ maxWidth: 320 }}>{p.rationale || '—'}</td>
                  <td>{status}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {showActions && (
                      <>
                        <button
                          onClick={() => onApprove(p.id)}
                          disabled={busyId === p.id}
                          style={{ marginRight: 6 }}
                        >
                          Approve
                        </button>
                        <button onClick={() => onReject(p.id)} disabled={busyId === p.id}>
                          Reject
                        </button>
                      </>
                    )}
                    {p.rejection_reason && (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                        {p.rejection_reason}
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
