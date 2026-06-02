import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  AnalysisFlow,
  ActiveAnalysisRun,
  FlowComponentKey,
  FlowComponentState,
  FlowComponentStatus,
} from '../types'
import { getAnalysisFlows, getActiveAnalysisRuns } from '../api'

type SourceLane = {
  key: 'market' | 'social' | 'news' | 'fundamentals'
  title: string
  feeds: string[]
  target: FlowComponentKey
  tone: 'market' | 'social' | 'news' | 'fundamentals'
}

const SOURCE_LANES: SourceLane[] = [
  { key: 'market',       title: 'Market',       feeds: ['Yahoo Finance', 'TradingView', 'MT5 ticks'], target: 'market_analyst',       tone: 'market' },
  { key: 'social',       title: 'Social Media', feeds: ['X / Twitter', 'Reddit', 'EODHD'],            target: 'sentiment_analyst',    tone: 'social' },
  { key: 'news',         title: 'News',         feeds: ['Bloomberg', 'Reuters', 'Finnhub'],           target: 'news_analyst',         tone: 'news' },
  { key: 'fundamentals', title: 'Fundamentals', feeds: ['Company profile', 'Financial history', 'Insider trxns'], target: 'fundamentals_analyst', tone: 'fundamentals' },
]

const COMPONENT_LABELS: Record<FlowComponentKey, string> = {
  market_analyst:       'Market Analyst',
  sentiment_analyst:    'Sentiment',
  news_analyst:         'News Analyst',
  fundamentals_analyst: 'Fundamentals',
  bull_researcher:      'Bullish',
  bear_researcher:      'Bearish',
  research_manager:     'Research Manager',
  trader:               'Trader',
  aggressive_risk:      'Aggressive',
  neutral_risk:         'Neutral',
  conservative_risk:    'Conservative',
  portfolio_manager:    'Manager',
}

/** Plain-English description of what each agent does and what its output means. */
const COMPONENT_ROLES: Record<FlowComponentKey, { role: string; research: string }> = {
  market_analyst: {
    role: 'Reads price action, indicators, and recent ticks to characterize the technical setup.',
    research: 'Pulls historical OHLC, key moving averages, momentum and volatility readings from MT5/Yahoo Finance.',
  },
  sentiment_analyst: {
    role: 'Gauges crowd positioning from social-media chatter and retail behavior.',
    research: 'Surveys X/Reddit posts and EODHD social signals for this symbol over the lookback window.',
  },
  news_analyst: {
    role: 'Distills the latest news flow into actionable themes.',
    research: 'Fetches recent headlines from Bloomberg, Reuters, and Finnhub; clusters by topic and ranks by impact.',
  },
  fundamentals_analyst: {
    role: 'Examines the issuer\'s financials and macro backdrop (when applicable).',
    research: 'Loads company profile, recent earnings, balance-sheet ratios, and insider transactions.',
  },
  bull_researcher: {
    role: 'Argues the long case using the analysts\' findings.',
    research: 'Cross-references bullish setups in technical/news/social data and constructs the strongest pro-trade thesis.',
  },
  bear_researcher: {
    role: 'Argues the short case using the same evidence.',
    research: 'Looks for downside catalysts, weakening momentum, and risk signals the bull case glosses over.',
  },
  research_manager: {
    role: 'Adjudicates the bull vs. bear debate and writes the consensus call.',
    research: 'Weighs both researchers\' arguments against historical accuracy and assigns a tentative directional bias.',
  },
  trader: {
    role: 'Converts the consensus into a concrete trade idea (direction, entry zone, stop, target).',
    research: 'Translates the research-manager\'s thesis into broker-executable order parameters.',
  },
  aggressive_risk: {
    role: 'Stress-tests the trade idea from a high-conviction lens.',
    research: 'Argues for taking the trade with full size — pushes back when the team is being too conservative.',
  },
  neutral_risk: {
    role: 'Balances conviction against drawdown discipline.',
    research: 'Validates sizing and stop placement against typical historical volatility.',
  },
  conservative_risk: {
    role: 'Voices the downside scenarios and minimum acceptable conditions.',
    research: 'Surfaces black-swan risks, correlation exposure, and reasons to pass on the trade.',
  },
  portfolio_manager: {
    role: 'Final approver — issues the BUY / SELL / HOLD verdict and reasoning.',
    research: 'Synthesizes the risk panel debate into a single decision the execution engine can act on.',
  },
}

/** Map raw component status to a sentence the operator can read at a glance. */
function statusEnglish(status: FlowComponentStatus): string {
  switch (status) {
    case 'pending':  return 'Has not run yet for this analysis.'
    case 'running':  return 'Currently working — output will stream in as it completes.'
    case 'done':     return 'Completed successfully. Verdict shown above; full reasoning below.'
    case 'failed':   return 'Errored before producing a verdict. See the output for the failure details.'
    case 'skipped':  return 'Not applicable to this run (e.g. fundamentals on a forex pair).'
    default:         return ''
  }
}

/** Heuristic verdict extractor — looks for the standard rating words the agents use. */
function extractVerdict(text: string): string | null {
  if (!text) return null
  // Look at the last 600 chars where the final call usually sits, then fall back to the whole text.
  const tail = text.slice(-600)
  const patterns: Array<[RegExp, string]> = [
    [/\b(?:STRONG\s+)?BUY\b/i,   'BUY'],
    [/\b(?:STRONG\s+)?SELL\b/i,  'SELL'],
    [/\bHOLD\b/i,                'HOLD'],
    [/\bBULLISH\b/i,             'BULLISH'],
    [/\bBEARISH\b/i,             'BEARISH'],
    [/\bOVERWEIGHT\b/i,          'OVERWEIGHT'],
    [/\bUNDERWEIGHT\b/i,         'UNDERWEIGHT'],
    [/\bNEUTRAL\b/i,             'NEUTRAL'],
  ]
  for (const [re, label] of patterns) if (re.test(tail)) return label
  for (const [re, label] of patterns) if (re.test(text)) return label
  return null
}

function fmtEpoch(s?: number | null): string {
  if (!s) return '—'
  try { return new Date(s * 1000).toLocaleString() } catch { return '—' }
}

function fmtDuration(start?: number | null, end?: number | null): string {
  if (!start || !end || end < start) return '—'
  const secs = Math.max(0, Math.round(end - start))
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  return `${m}m ${secs - m * 60}s`
}

const ALL_KEYS: FlowComponentKey[] = [
  'market_analyst','sentiment_analyst','news_analyst','fundamentals_analyst',
  'bull_researcher','bear_researcher','research_manager','trader',
  'aggressive_risk','neutral_risk','conservative_risk','portfolio_manager',
]

function summarize(text: string, limit = 140): string {
  const compact = (text || '').replace(/\s+/g, ' ').trim()
  if (!compact) return ''
  return compact.length > limit ? `${compact.slice(0, limit)}…` : compact
}

function signalClass(signal: string | null | undefined) {
  const s = (signal || '').toUpperCase()
  if (s === 'BUY') return 'executed'
  if (s === 'SELL') return 'failed'
  if (s === 'HOLD') return 'pending'
  return 'open'
}

/** Synthesize a static "completed" run shape from a saved AnalysisFlow row,
 *  so the live + historical views share one rendering path. */
function flowToSyntheticRun(flow: AnalysisFlow): ActiveAnalysisRun {
  // Historical traces only carry one wall-clock for the whole flow, so we use
  // it as a shared anchor — the detail panel can at least show "when this
  // analysis ran" even though we can't show per-component durations.
  const anchorMs = flow.trace?.timestamp
    ? new Date(flow.trace.timestamp).getTime()
    : flow.decided_at ? new Date(flow.decided_at).getTime() : 0
  const anchorSec = anchorMs > 0 ? Math.round(anchorMs / 1000) : 0

  const components = {} as Record<FlowComponentKey, FlowComponentState>
  ALL_KEYS.forEach(key => {
    const full = (flow.trace?.components?.[key] || '').trim()
    components[key] = {
      status: full ? 'done' : 'skipped',
      preview: summarize(full),
      full_text: full,
      updated_at: anchorSec,
      started_at: full ? anchorSec : null,
      completed_at: full ? anchorSec : null,
    }
  })
  return {
    run_id: `flow-${flow.id}`,
    symbol: flow.symbol,
    started_at: 0,
    finished_at: 0,
    status: flow.success ? 'success' : 'error',
    stage_label: flow.success ? 'Completed' : (flow.error || 'Failed'),
    active_component: null,
    error: flow.error,
    signal: flow.signal,
    elapsed_seconds: 0,
    components,
  }
}

/** How many of `applicable` components are done — used for the percent bar. */
function progressPercent(run: ActiveAnalysisRun): number {
  const states = Object.values(run.components)
  const eligible = states.filter(s => s.status !== 'skipped')
  if (eligible.length === 0) return 0
  const done = eligible.filter(s => s.status === 'done').length
  return Math.round((done / eligible.length) * 100)
}

// ─── Architecture diagram ────────────────────────────────────────────────────

function NodeCard({
  componentKey,
  state,
  emphasize,
  onClick,
  selected,
  variant,
}: {
  componentKey: FlowComponentKey
  state: FlowComponentState
  emphasize?: 'bull' | 'bear' | 'neutral' | 'risk' | 'manager' | 'trader'
  onClick: () => void
  selected: boolean
  variant?: string
}) {
  const status: FlowComponentStatus = state?.status ?? 'pending'
  const classes = [
    'arch-node',
    `arch-node-${status}`,
    emphasize ? `arch-node-${emphasize}` : '',
    variant ? `arch-node-${variant}` : '',
    selected ? 'arch-node-selected' : '',
  ].filter(Boolean).join(' ')
  return (
    <button type="button" className={classes} onClick={onClick}>
      <div className="arch-node-status">
        <span className={`arch-dot arch-dot-${status}`} />
        <span className="arch-node-status-label">{status}</span>
      </div>
      <div className="arch-node-title">{COMPONENT_LABELS[componentKey]}</div>
      {state?.preview && <div className="arch-node-preview">{state.preview}</div>}
    </button>
  )
}

function SourceLaneCard({
  lane,
  state,
  active,
}: {
  lane: SourceLane
  state: FlowComponentState
  active: boolean
}) {
  const status = state?.status ?? 'pending'
  return (
    <div className={`arch-source arch-source-${lane.tone} arch-source-${status} ${active ? 'arch-source-active' : ''}`}>
      <div className="arch-source-rail" />
      <div className="arch-source-title">{lane.title}</div>
      <div className="arch-source-feeds">
        {lane.feeds.map(f => <span key={f} className="arch-source-chip">{f}</span>)}
      </div>
    </div>
  )
}

function ArchitectureDiagram({
  run,
  selectedKey,
  onSelect,
}: {
  run: ActiveAnalysisRun
  selectedKey: FlowComponentKey
  onSelect: (key: FlowComponentKey) => void
}) {
  const components = run.components
  const isActive = (k: FlowComponentKey) => run.active_component === k || components[k]?.status === 'running'

  return (
    <div className="arch-diagram">
      {/* Column 1: sources */}
      <div className="arch-col arch-col-sources">
        {SOURCE_LANES.map(lane => (
          <SourceLaneCard
            key={lane.key}
            lane={lane}
            state={components[lane.target]}
            active={isActive(lane.target)}
          />
        ))}
      </div>

      {/* Column 2: analysts (one card per source's analyst) */}
      <div className="arch-col arch-col-analysts">
        {SOURCE_LANES.map(lane => (
          <NodeCard
            key={lane.target}
            componentKey={lane.target}
            state={components[lane.target]}
            variant={`analyst-${lane.tone}`}
            onClick={() => onSelect(lane.target)}
            selected={selectedKey === lane.target}
          />
        ))}
      </div>

      {/* Column 3: researcher team (bull/bear with discussion arrows) */}
      <div className="arch-col arch-col-researchers">
        <div className="arch-team arch-team-research">
          <div className="arch-team-title">Researcher Team</div>
          <NodeCard
            componentKey="bull_researcher"
            state={components['bull_researcher']}
            emphasize="bull"
            onClick={() => onSelect('bull_researcher')}
            selected={selectedKey === 'bull_researcher'}
          />
          <div className="arch-discussion">
            <span className="arch-arrow arch-arrow-down">↓</span>
            <span className="arch-discussion-label">Discussion</span>
            <span className="arch-arrow arch-arrow-up">↑</span>
          </div>
          <NodeCard
            componentKey="bear_researcher"
            state={components['bear_researcher']}
            emphasize="bear"
            onClick={() => onSelect('bear_researcher')}
            selected={selectedKey === 'bear_researcher'}
          />
          <NodeCard
            componentKey="research_manager"
            state={components['research_manager']}
            emphasize="manager"
            onClick={() => onSelect('research_manager')}
            selected={selectedKey === 'research_manager'}
          />
        </div>
      </div>

      {/* Column 4: trader + risk team stacked */}
      <div className="arch-col arch-col-trader">
        <NodeCard
          componentKey="trader"
          state={components['trader']}
          emphasize="trader"
          onClick={() => onSelect('trader')}
          selected={selectedKey === 'trader'}
        />
        <div className="arch-team arch-team-risk">
          <div className="arch-team-title">Risk Management Team</div>
          <NodeCard
            componentKey="aggressive_risk"
            state={components['aggressive_risk']}
            emphasize="bull"
            onClick={() => onSelect('aggressive_risk')}
            selected={selectedKey === 'aggressive_risk'}
          />
          <NodeCard
            componentKey="neutral_risk"
            state={components['neutral_risk']}
            emphasize="neutral"
            onClick={() => onSelect('neutral_risk')}
            selected={selectedKey === 'neutral_risk'}
          />
          <NodeCard
            componentKey="conservative_risk"
            state={components['conservative_risk']}
            emphasize="bear"
            onClick={() => onSelect('conservative_risk')}
            selected={selectedKey === 'conservative_risk'}
          />
        </div>
      </div>

      {/* Column 5: manager + execution */}
      <div className="arch-col arch-col-final">
        <NodeCard
          componentKey="portfolio_manager"
          state={components['portfolio_manager']}
          emphasize="manager"
          onClick={() => onSelect('portfolio_manager')}
          selected={selectedKey === 'portfolio_manager'}
        />
        <div className={`arch-execution arch-execution-${run.status}`}>
          <div className="arch-execution-title">Execution</div>
          <div className="arch-execution-signal">{run.signal || (run.status === 'running' ? '…' : '—')}</div>
          <div className="arch-execution-status">{run.stage_label}</div>
        </div>
      </div>
    </div>
  )
}

// ─── Component detail panel ─────────────────────────────────────────────────

function ComponentDetailPanel({
  componentKey,
  status,
  fullText,
  startedAt,
  completedAt,
  runError,
}: {
  componentKey: FlowComponentKey
  status: FlowComponentStatus
  fullText: string
  startedAt?: number | null
  completedAt?: number | null
  runError: string | null
}) {
  const role = COMPONENT_ROLES[componentKey]
  const verdict = extractVerdict(fullText)
  const duration = fmtDuration(startedAt, completedAt)
  const hasOutput = fullText.trim().length > 0

  return (
    <section className="arch-detail">
      <div className="arch-detail-header">
        <h3>{COMPONENT_LABELS[componentKey]}</h3>
        <span className={`arch-detail-status arch-detail-status-${status}`}>{status}</span>
      </div>

      <div className="arch-detail-grid">
        <div className="arch-detail-block">
          <div className="arch-detail-label">Role</div>
          <p>{role?.role || '—'}</p>
        </div>
        <div className="arch-detail-block">
          <div className="arch-detail-label">Research performed</div>
          <p>{role?.research || '—'}</p>
        </div>
        <div className="arch-detail-block">
          <div className="arch-detail-label">Status</div>
          <p>{statusEnglish(status)}</p>
        </div>
        <div className="arch-detail-block">
          <div className="arch-detail-label">Verdict</div>
          {verdict ? (
            <p>
              <span className={`action-badge ${signalClass(verdict)}`} style={{ marginRight: 8 }}>
                {verdict}
              </span>
              detected in the output.
            </p>
          ) : (
            <p>{hasOutput ? 'No explicit verdict word found in the output.' : '—'}</p>
          )}
        </div>
        <div className="arch-detail-block">
          <div className="arch-detail-label">Started</div>
          <p className="number-font">{fmtEpoch(startedAt)}</p>
        </div>
        <div className="arch-detail-block">
          <div className="arch-detail-label">Finished</div>
          <p className="number-font">{fmtEpoch(completedAt)}</p>
        </div>
        <div className="arch-detail-block">
          <div className="arch-detail-label">Duration</div>
          <p className="number-font">{duration}</p>
        </div>
        <div className="arch-detail-block">
          <div className="arch-detail-label">Output size</div>
          <p className="number-font">{hasOutput ? `${fullText.length.toLocaleString()} chars` : '—'}</p>
        </div>
      </div>

      {status === 'failed' && runError && (
        <div className="alert-banner" style={{ margin: '12px 0 0' }}>
          ⚠️ Run error: {runError}
        </div>
      )}

      <div className="arch-detail-output">
        <div className="arch-detail-label">Full output</div>
        {hasOutput ? (
          <pre className="arch-detail-pre">{fullText}</pre>
        ) : (
          <p style={{ color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
            {status === 'skipped'
              ? 'This component was skipped — nothing to display.'
              : status === 'running'
              ? 'Output streams here when the agent finishes its work.'
              : 'No output captured for this component.'}
          </p>
        )}
      </div>
    </section>
  )
}


// ─── Page ────────────────────────────────────────────────────────────────────

export function AnalysisFlowPanel() {
  const [flows, setFlows] = useState<AnalysisFlow[]>([])
  const [activeRuns, setActiveRuns] = useState<ActiveAnalysisRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedKey, setSelectedKey] = useState<FlowComponentKey>('portfolio_manager')
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [symbolFilter, setSymbolFilter] = useState('')
  const pollTimer = useRef<number | null>(null)

  // Poll completed flows (slow).
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getAnalysisFlows({ limit: 30, symbol: symbolFilter.trim() || undefined })
      .then(rows => { if (!cancelled) { setFlows(rows); setError(null) } })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load analysis flow') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbolFilter])

  // Poll active runs (fast) — 1s while there's anything in flight, 3s otherwise.
  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const runs = await getActiveAnalysisRuns()
        if (cancelled) return
        setActiveRuns(runs)
      } catch {/* ignore transient errors */}
      if (cancelled) return
      // Adaptive cadence: while a run is in flight we want every component
      // transition to surface near-instantly, so poll at ~600ms. While idle
      // we still poll fast (1.2s) so a Trade-button click pops a fresh run
      // onto the Flow page within a single user-perceptible beat.
      const anyRunning = activeRunsRef.current.some(r => r.status === 'running')
      pollTimer.current = window.setTimeout(tick, anyRunning ? 600 : 1200)
    }
    tick()
    return () => {
      cancelled = true
      if (pollTimer.current != null) window.clearTimeout(pollTimer.current)
    }
  }, [])

  const activeRunsRef = useRef<ActiveAnalysisRun[]>([])
  useEffect(() => { activeRunsRef.current = activeRuns }, [activeRuns])

  // Unified list: live runs first, then last 20 completed flows.
  const allRuns: ActiveAnalysisRun[] = useMemo(() => {
    const filterSym = symbolFilter.trim().toUpperCase()
    const filtered = (rs: ActiveAnalysisRun[]) =>
      filterSym ? rs.filter(r => r.symbol.toUpperCase().includes(filterSym)) : rs
    return [
      ...filtered(activeRuns),
      ...filtered(flows.map(flowToSyntheticRun)),
    ]
  }, [activeRuns, flows, symbolFilter])

  // Track which run is selected — prefer a running one if available.
  useEffect(() => {
    if (allRuns.length === 0) { setSelectedRunId(null); return }
    if (!selectedRunId || !allRuns.find(r => r.run_id === selectedRunId)) {
      const live = allRuns.find(r => r.status === 'running')
      setSelectedRunId((live ?? allRuns[0]).run_id)
    }
  }, [allRuns, selectedRunId])

  const selectedRun = useMemo(
    () => allRuns.find(r => r.run_id === selectedRunId) ?? allRuns[0] ?? null,
    [allRuns, selectedRunId],
  )

  // If the selected component has no preview, jump to one that does.
  useEffect(() => {
    if (!selectedRun) return
    const cur = selectedRun.components[selectedKey]
    if (cur && cur.preview) return
    const next = ALL_KEYS.find(k => selectedRun.components[k]?.preview)
    if (next) setSelectedKey(next)
  }, [selectedRun, selectedKey])

  const detailState = selectedRun?.components[selectedKey]
  const detailStatus: FlowComponentStatus = detailState?.status || 'pending'
  const detailFullText = (detailState?.full_text || detailState?.preview || '').trim()

  return (
    <div className="analysis-flow-page arch-page">
      <div className="flow-toolbar">
        <div>
          <h2>Trade Analysis Flow</h2>
          <p>Live architecture view of the TradingAgents pipeline. Updates as the LangGraph executes each component.</p>
        </div>
        <div className="flow-filter">
          <input
            type="text"
            value={symbolFilter}
            onChange={e => { setSelectedRunId(null); setSymbolFilter(e.target.value.toUpperCase()) }}
            placeholder="Filter symbol"
            aria-label="Filter symbol"
          />
          <button className="btn btn-ghost" onClick={() => setSymbolFilter('')}>Clear</button>
        </div>
      </div>

      {error && <div className="alert-banner">{error}</div>}

      <div className="arch-layout">
        <aside className="arch-run-list">
          <div className="flow-section-title">Runs</div>
          {loading && allRuns.length === 0 && <div className="flow-empty">Loading…</div>}
          {!loading && allRuns.length === 0 && <div className="flow-empty">No runs to display.</div>}
          {allRuns.map(run => {
            const pct = progressPercent(run)
            const isLive = run.status === 'running'
            return (
              <button
                type="button"
                key={run.run_id}
                className={`arch-run-item ${selectedRun?.run_id === run.run_id ? 'active' : ''} ${isLive ? 'live' : ''}`}
                onClick={() => setSelectedRunId(run.run_id)}
              >
                <span className="arch-run-top">
                  <span className="symbol-badge">{run.symbol}</span>
                  {isLive ? (
                    <span className="arch-live-pill"><span className="arch-live-dot" />LIVE</span>
                  ) : (
                    <span className={`action-badge ${signalClass(run.signal)}`}>{run.signal || '—'}</span>
                  )}
                </span>
                <span className="arch-run-stage">{run.stage_label}</span>
                <div className="arch-run-bar"><div className="arch-run-bar-fill" style={{ width: `${pct}%` }} /></div>
                <span className="arch-run-meta">
                  {isLive
                    ? `${pct}% • ${Math.round(run.elapsed_seconds)}s elapsed`
                    : (run.error ? run.error : (run.signal ? `Final: ${run.signal}` : 'Completed'))}
                </span>
              </button>
            )
          })}
        </aside>

        <main className="arch-main">
          {selectedRun ? (
            <>
              <div className="arch-summary">
                <div className="arch-summary-left">
                  <span className="symbol-badge">{selectedRun.symbol}</span>
                  {selectedRun.status === 'running'
                    ? <span className="arch-live-pill"><span className="arch-live-dot" />LIVE</span>
                    : <span className={`action-badge ${signalClass(selectedRun.signal)}`}>{selectedRun.signal || '—'}</span>}
                  <span className="arch-summary-stage">{selectedRun.stage_label}</span>
                </div>
                <div className="arch-summary-right">
                  <span>Progress: {progressPercent(selectedRun)}%</span>
                  <span>Elapsed: {Math.round(selectedRun.elapsed_seconds)}s</span>
                </div>
              </div>

              <ArchitectureDiagram
                run={selectedRun}
                selectedKey={selectedKey}
                onSelect={setSelectedKey}
              />

              <ComponentDetailPanel
                componentKey={selectedKey}
                status={detailStatus}
                fullText={detailFullText}
                startedAt={detailState?.started_at}
                completedAt={detailState?.completed_at}
                runError={selectedRun.error}
              />
            </>
          ) : (
            <div className="flow-empty large">Trigger an analysis to populate the flow.</div>
          )}
        </main>
      </div>
    </div>
  )
}
