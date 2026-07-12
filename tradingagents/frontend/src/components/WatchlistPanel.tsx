import { useEffect, useState } from 'react'
import type { WatchlistEntry } from '../types'
import { triggerAnalysis, addToWatchlist, addManyToWatchlist, removeFromWatchlist } from '../api'
import { useBrokerSymbols } from '../useBrokerSymbols'

/** How long a completed/failed status sticks around before we hide it. */
const STATUS_TTL_MS = 5 * 60 * 1000  // 5 minutes

/** True when the ISO timestamp is missing OR more than STATUS_TTL_MS old. */
function isStale(isoTime: string | null | undefined, now: number): boolean {
  if (!isoTime) return false  // unknown age — treat as fresh so we don't hide live messages
  const t = Date.parse(isoTime)
  if (Number.isNaN(t)) return false
  return now - t > STATUS_TTL_MS
}

interface WatchlistPanelProps {
  entries: WatchlistEntry[]
  onRefresh: () => void
}

type ActionStatus = {
  state: 'running' | 'success' | 'error'
  message: string
  progressPercent?: number
}

function SignalBadge({ signal }: { signal: string | null }) {
  if (!signal || signal === 'UNKNOWN') {
    return <span style={{ color: 'var(--color-text-muted)' }}>-</span>
  }

  const palette =
    signal === 'BUY'
      ? { bg: 'var(--color-profit-dim)', fg: 'var(--color-profit)', border: 'color-mix(in srgb, var(--color-profit) 40%, transparent 60%)' }
      : signal === 'SELL'
      ? { bg: 'var(--color-loss-dim)', fg: 'var(--color-loss)', border: 'color-mix(in srgb, var(--color-loss) 40%, transparent 60%)' }
      : { bg: 'var(--color-warning-dim)', fg: 'var(--color-warning)', border: 'color-mix(in srgb, var(--color-warning) 40%, transparent 60%)' }

  return (
    <span style={{
      display: 'inline-block',
      padding: '4px 10px',
      borderRadius: 999,
      background: palette.bg,
      color: palette.fg,
      border: `1px solid ${palette.border}`,
      fontWeight: 700,
      fontSize: '0.74rem',
      letterSpacing: '0.08em',
    }}>
      {signal}
    </span>
  )
}

function ModeBadge({ mode }: { mode: string }) {
  const palette =
    mode === 'commodity'
      ? { bg: 'var(--color-gold-dim)', fg: 'var(--color-gold)', border: 'color-mix(in srgb, var(--color-gold) 35%, transparent 65%)' }
      : mode === 'crypto'
      ? { bg: 'color-mix(in srgb, var(--color-profit) 14%, transparent 86%)', fg: 'var(--color-profit)', border: 'color-mix(in srgb, var(--color-profit) 35%, transparent 65%)' }
      : mode === 'index'
      ? { bg: 'color-mix(in srgb, var(--color-warning) 14%, transparent 86%)', fg: 'var(--color-warning)', border: 'color-mix(in srgb, var(--color-warning) 35%, transparent 65%)' }
      : mode === 'forex'
      ? { bg: 'var(--color-primary-glow)', fg: 'var(--color-primary)', border: 'color-mix(in srgb, var(--color-primary) 35%, transparent 65%)' }
      : { bg: 'color-mix(in srgb, var(--color-info) 14%, transparent 86%)', fg: 'var(--color-info)', border: 'color-mix(in srgb, var(--color-info) 35%, transparent 65%)' }

  return (
    <span style={{
      display: 'inline-block',
      padding: '3px 9px',
      borderRadius: 6,
      background: palette.bg,
      color: palette.fg,
      border: `1px solid ${palette.border}`,
      fontSize: '0.7rem',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
    }}>
      {mode}
    </span>
  )
}

function resultMessage(entry: WatchlistEntry): string | null {
  const result = entry.latest_result
  if (!result) return null
  if (!result.success) {
    if (!result.error) return 'Last run failed'
    const modelMatch = result.error.match(/model ['"]([^'"]+)['"] not found/i)
    if (modelMatch) return `Last run failed: model ${modelMatch[1]} not found`
    const messageMatch = result.error.match(/['"]message['"]:\s*['"]([^'"]+)['"]/i)
    if (messageMatch) return `Last run failed: ${messageMatch[1]}`
    return `Last run failed: ${result.error}`
  }
  if (result.execution?.status) {
    const reason = result.execution.reason ? `: ${result.execution.reason}` : ''
    return `Result: ${result.signal}. Trade ${result.execution.status}${reason}`
  }
  return `Result: ${result.signal}`
}

function displaySignal(entry: WatchlistEntry, status?: ActionStatus): string | null {
  const job = entry.analysis_job
  if (status?.state === 'running' || job?.status === 'running' || job?.status === 'queued') {
    return entry.last_signal && entry.last_signal !== 'UNKNOWN' ? entry.last_signal : null
  }
  const signal = entry.last_signal || entry.latest_result?.signal || null
  return signal === 'UNKNOWN' ? null : signal
}

export function WatchlistPanel({ entries, onRefresh }: WatchlistPanelProps) {
  const [newSymbol, setNewSymbol] = useState('')
  const [triggering, setTriggering] = useState<string | null>(null)
  const [trading, setTrading] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [actionStatus, setActionStatus] = useState<Record<string, ActionStatus & { completedAt?: number }>>({})
  // Tick state so the staleness check re-evaluates without a parent re-render.
  // Updates every 30s — finer than the 5-min TTL, so messages disappear cleanly.
  const [, setNow] = useState(Date.now())
  const broker = useBrokerSymbols()

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [])

  // Drop any local actionStatus entries whose completedAt is older than the TTL.
  useEffect(() => {
    const id = window.setInterval(() => {
      const cutoff = Date.now() - STATUS_TTL_MS
      setActionStatus(current => {
        const next: typeof current = {}
        let changed = false
        for (const [symbol, status] of Object.entries(current)) {
          if (status.state === 'running' || !status.completedAt || status.completedAt > cutoff) {
            next[symbol] = status
          } else {
            changed = true
          }
        }
        return changed ? next : current
      })
    }, 30_000)
    return () => window.clearInterval(id)
  }, [])

  async function handleTrigger(symbol: string, executeTrade = false) {
    if (executeTrade) setTrading(symbol)
    else setTriggering(symbol)

    // Auto-force when the row already shows an in-flight job for this symbol.
    // The previous thread is either making progress (rare to click Run again
    // in that case) or stuck waiting on a slow LLM/vendor. Either way the user
    // pressing Run again means "I want fresh data now" — so we cancel the
    // prior run and bypass the scheduler's serial lock.
    const entry = entries.find(e => e.symbol === symbol)
    const priorJob = entry?.analysis_job
    const priorInflight = priorJob?.status === 'queued' || priorJob?.status === 'running'
    const force = priorInflight

    setActionStatus(current => ({
      ...current,
          [symbol]: {
            state: 'running',
            message: force
              ? (executeTrade ? 'Cancelling stuck run, retrying trade…' : 'Cancelling stuck run, restarting…')
              : (executeTrade ? 'Trade analysis queued' : 'Analysis queued'),
            progressPercent: 5,
          },
        }))

    try {
      const completed = await triggerAnalysis(symbol, executeTrade, force)
      const result = completed.result
      const execution = result?.execution
      const executionText = execution?.ticket
        ? ` · ticket #${execution.ticket}`
        : execution?.reason ? ` · ${execution.reason}` : ''
      setActionStatus(current => ({
        ...current,
        [symbol]: {
          state: execution?.status === 'failed' ? 'error' : 'success',
          message: `${result?.signal ?? 'Completed'}${executionText}`,
          progressPercent: 100,
          completedAt: Date.now(),
        },
      }))
      onRefresh()
    } catch (error) {
      setActionStatus(current => ({
        ...current,
        [symbol]: {
          state: 'error',
          message: error instanceof Error ? error.message : String(error),
          progressPercent: 100,
          completedAt: Date.now(),
        },
      }))
    } finally {
      setTriggering(null)
      setTrading(null)
    }
  }

  // Mock BUY/SELL execution is intentionally unavailable in the production UI.

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    const symbols = newSymbol
      .split(/[\s,;\n]+/)
      .map(s => s.trim().toUpperCase())
      .filter(Boolean)
    if (symbols.length === 0) return
    setAdding(true)
    try {
      if (symbols.length === 1) {
        await addToWatchlist(symbols[0])
      } else {
        await addManyToWatchlist(symbols)
      }
      setNewSymbol('')
      onRefresh()
    } finally {
      setAdding(false)
    }
  }

  async function handleRemove(symbol: string) {
    await removeFromWatchlist(symbol)
    onRefresh()
  }

  return (
    <div>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 16,
        gap: 12,
        flexWrap: 'wrap',
      }}>
        <div className="card-title" style={{ marginBottom: 0 }}>
          Watchlist - TradingView Monitored Symbols
        </div>
        <form onSubmit={handleAdd} style={{ display: 'flex', gap: 8 }}>
          <input
            list="broker-symbols-watchlist"
            value={newSymbol}
            onChange={e => setNewSymbol(e.target.value.toUpperCase())}
            placeholder={
              broker.symbols.length > 0
                ? `Search ${broker.symbols.length.toLocaleString()} broker symbols...`
                : 'e.g. EURUSD, GBPJPY, XAUUSD'
            }
            title="Add one or many symbols. Autocomplete pulls from the connected broker."
            style={{ width: 280 }}
          />
          <datalist id="broker-symbols-watchlist">
            {broker.symbols.slice(0, 1500).map(s => (
              <option key={s.name} value={s.name}>{s.description}</option>
            ))}
          </datalist>
          <button type="submit" disabled={adding} className="btn">
            {adding ? '...' : '+ Add'}
          </button>
        </form>
      </div>

      {entries.length === 0 ? (
        <div style={{
          color: 'var(--color-text-muted)',
          padding: 24,
          textAlign: 'center',
        }}>
          No symbols in watchlist
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Type</th>
                <th>Data Source</th>
                <th>Analysts</th>
                <th>Interval</th>
                <th>Last Analysis</th>
                <th>Signal</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(entry => {
                const now = Date.now()
                const status = actionStatus[entry.symbol]
                const job = entry.analysis_job
                const jobRunning = job?.status === 'queued' || job?.status === 'running'
                const jobFailed = job?.status === 'failed' || job?.status === 'timeout'
                // 5-minute freshness gate on the backend-provided job status —
                // keeps the row clean once a stale "timed out" sits long enough
                // that the user has moved on.
                const jobStale = !jobRunning && isStale(job?.completed_at ?? job?.updated_at, now)
                const jobStatus = job && !jobStale
                  ? {
                      state: jobRunning ? 'running' : jobFailed ? 'error' : 'success',
                      message: job.message,
                      progressPercent: job.progress_percent,
                    } satisfies ActionStatus
                  : undefined
                // Same TTL for the persisted last-result blurb and for our
                // local actionStatus snapshot, so all three sources agree.
                const persistedMessage = isStale(entry.latest_result?.timestamp, now)
                  ? null
                  : resultMessage(entry)
                const localStatusFresh = status && (status.state === 'running' || !status.completedAt || now - status.completedAt <= STATUS_TTL_MS)
                  ? status
                  : undefined
                const effectiveStatus = jobRunning ? jobStatus : (localStatusFresh || jobStatus)
                const progressPercent = effectiveStatus?.progressPercent
                const statusMessage = effectiveStatus?.message
                  ? progressPercent != null
                    ? `${effectiveStatus.message} (${progressPercent}%)`
                    : effectiveStatus.message
                  : persistedMessage
                return (
                  <tr key={entry.symbol}>
                    <td>
                      <div>
                        <span className="symbol-badge">{entry.symbol}</span>
                        <div style={{
                          fontSize: '0.72rem',
                          color: 'var(--color-text-muted)',
                          marginTop: 4,
                        }}>
                          {entry.display_name}
                        </div>
                      </div>
                    </td>
                    <td><ModeBadge mode={entry.mode} /></td>
                    <td>
                      <span style={{
                        fontSize: '0.8rem',
                        color: entry.use_tradingview ? 'var(--color-profit)' : 'var(--color-text-muted)',
                        fontWeight: entry.use_tradingview ? 600 : 400,
                      }}>
                        {entry.use_tradingview ? 'TradingView' : 'yfinance'}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                        {entry.analysts.join(', ')}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--color-text-dim)' }}>
                      {entry.interval_minutes ? `${entry.interval_minutes}m` : `${entry.interval_hours}h`}
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                      {entry.last_analysis || entry.latest_result?.timestamp
                        ? new Date(entry.last_analysis || entry.latest_result!.timestamp).toLocaleString()
                        : <span style={{ color: 'var(--color-warning)' }}>Not yet</span>}
                    </td>
                    <td style={{ minWidth: 110 }}>
                      <SignalBadge signal={displaySignal(entry, effectiveStatus)} />
                    </td>
                    <td>
                      <div>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button
                            onClick={() => handleTrigger(entry.symbol, true)}
                            disabled={triggering === entry.symbol || trading === entry.symbol || jobRunning}
                            title="Run the local Codex strategy and execute only a safety-qualified BUY or SELL"
                            className="btn btn-trade"
                            style={{ padding: '5px 12px', fontSize: '0.76rem' }}
                          >
                            {trading === entry.symbol ? '...' : '> Run & Trade'}
                          </button>
                          <button
                            onClick={() => handleRemove(entry.symbol)}
                            title="Remove from watchlist"
                            className="btn btn-danger"
                            style={{ padding: '5px 10px', fontSize: '0.76rem' }}
                          >
                            x
                          </button>
                        </div>
                        {/* Mock BUY/SELL controls intentionally hidden. */}
                        <div
                          title={statusMessage || undefined}
                          style={{
                            maxWidth: 260,
                            minHeight: '1rem',
                            marginTop: 6,
                            fontSize: '0.72rem',
                            lineHeight: 1.35,
                            color:
                              effectiveStatus
                                ? effectiveStatus.state === 'error'
                                  ? 'var(--color-loss)'
                                  : effectiveStatus.state === 'running'
                                  ? 'var(--color-warning)'
                                  : 'var(--color-text-muted)'
                                : entry.latest_result?.success === false
                                ? 'var(--color-loss)'
                                : 'var(--color-text-muted)',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            visibility: statusMessage ? 'visible' : 'hidden',
                          }}
                        >
                          {statusMessage || '-'}
                        </div>
                        <div
                          title={progressPercent != null ? `${progressPercent}% complete` : undefined}
                          style={{
                            width: 260,
                            height: 5,
                            marginTop: 5,
                            borderRadius: 999,
                            background: 'color-mix(in srgb, var(--color-border) 55%, transparent 45%)',
                            overflow: 'hidden',
                            visibility: progressPercent != null ? 'visible' : 'hidden',
                          }}
                        >
                          <div
                            style={{
                              width: `${progressPercent ?? 0}%`,
                              height: '100%',
                              borderRadius: 999,
                              background:
                                effectiveStatus?.state === 'error'
                                  ? 'var(--color-loss)'
                                  : effectiveStatus?.state === 'success'
                                  ? 'var(--color-profit)'
                                  : 'var(--color-warning)',
                              transition: 'width 0.25s ease',
                            }}
                          />
                        </div>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
