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
      <div className="card-title" style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span>Proposals</span>
        <select value={filter} onChange={(e) => setFilter(e.target.value as Filter)}>
          <option value="pending">Pending</option>
          <option value="applied">Applied</option>
          <option value="rejected">Rejected</option>
          <option value="all">All</option>
        </select>
      </div>

      {error && (
        <div className="alert-banner">⚠️ {error}</div>
      )}

      {rows.length === 0 ? (
        <div style={{ padding: 24, color: 'var(--color-text-muted)' }}>
          No {filter} proposals.
        </div>
      ) : (
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th>ID</th><th>Proposed at</th><th>Change</th><th>Rationale</th>
              <th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const key = p.diff ? Object.keys(p.diff)[0] : null
              const change = key
                ? `${key}: ${String(p.diff![key].from)} → ${String(p.diff![key].to)}`
                : '—'
              const status = p.applied
                ? <span className="action-badge executed">applied {fmtTs(p.applied_at)}</span>
                : p.rejected_at
                ? <span className="action-badge rejected">rejected {fmtTs(p.rejected_at)}</span>
                : <span className="action-badge pending">pending</span>
              const showActions = !p.applied && !p.rejected_at
              return (
                <tr key={p.id}>
                  <td style={{ color: 'var(--color-text-muted)' }}>{p.id}</td>
                  <td style={{ color: 'var(--color-text-dim)' }}>{fmtTs(p.proposed_at)}</td>
                  <td>
                    <code style={{
                      padding: '2px 8px',
                      borderRadius: 4,
                      background: 'var(--color-background)',
                      border: '1px solid var(--color-border)',
                      color: 'var(--color-primary)',
                      fontSize: '0.82rem',
                    }}>
                      {change}
                    </code>
                  </td>
                  <td style={{ maxWidth: 320, color: 'var(--color-text-dim)' }}>
                    {p.rationale || '—'}
                  </td>
                  <td>{status}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {showActions && (
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          onClick={() => onApprove(p.id)}
                          disabled={busyId === p.id}
                          className="btn"
                          style={{ padding: '5px 12px', fontSize: '0.78rem' }}
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => onReject(p.id)}
                          disabled={busyId === p.id}
                          className="btn btn-ghost"
                          style={{
                            padding: '5px 12px',
                            fontSize: '0.78rem',
                            color: 'var(--color-loss)',
                            borderColor: 'color-mix(in srgb, var(--color-loss) 50%, transparent 50%)',
                          }}
                        >
                          Reject
                        </button>
                      </div>
                    )}
                    {p.rejection_reason && (
                      <div style={{
                        fontSize: '0.78rem',
                        color: 'var(--color-text-muted)',
                        marginTop: 4,
                      }}>
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
