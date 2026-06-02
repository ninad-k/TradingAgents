import { useState, useEffect, useCallback, useRef } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { DashboardStatus, WatchlistEntry } from './types'
import { subscribeToLiveUpdates, getStatus, getWatchlist } from './api'
import { Dashboard } from './components/Dashboard'
import { ScoreboardPanel } from './components/Scoreboard'
import { DecisionsLedger } from './components/DecisionsLedger'
import { ProposalsPanel } from './components/Proposals'
import { LearnedParamsPanel } from './components/LearnedParams'
import { DashboardSkeleton } from './components/DashboardSkeleton'
import { AnalysisFlowPanel } from './components/AnalysisFlow'
import './App.css'

type Tab = 'overview' | 'flow' | 'scoreboard' | 'decisions' | 'proposals' | 'params'
type Theme = 'light' | 'dark'

/** Connection lifecycle:
 *  - `initial`    : first load, never had data yet — show skeleton, no error
 *  - `connecting` : reconnecting in background — keep stale data, no error
 *  - `live`       : WebSocket is delivering updates
 *  - `offline`    : retried > N times, surface an error banner
 */
type Connection = 'initial' | 'connecting' | 'live' | 'offline'

const THEME_KEY = 'tradingagents.theme'
const DEFAULT_THEME: Theme = 'light'

/* Retry-with-backoff: keep trying so a momentary network blip doesn't surface
   as a scary red banner on every page reload. Only after N seconds do we
   actually mark the connection as offline. */
const INITIAL_RETRY_MS = 800
const MAX_RETRY_MS = 6000
const OFFLINE_GRACE_MS = 8000
const REST_STEADY_POLL_MS = 10000

function statusDataKey(status: DashboardStatus): string {
  const { timestamp: _timestamp, ...stableStatus } = status
  return JSON.stringify(stableStatus)
}

function setStatusIfChanged(
  setter: Dispatch<SetStateAction<DashboardStatus | null>>,
  next: DashboardStatus,
) {
  setter(prev => {
    if (prev && statusDataKey(prev) === statusDataKey(next)) return prev
    return next
  })
}

function setWatchlistIfChanged(
  setter: Dispatch<SetStateAction<WatchlistEntry[]>>,
  next: WatchlistEntry[],
) {
  setter(prev => {
    if (JSON.stringify(prev) === JSON.stringify(next)) return prev
    return next
  })
}

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window === 'undefined') return DEFAULT_THEME
    const stored = window.localStorage.getItem(THEME_KEY) as Theme | null
    return stored === 'light' || stored === 'dark' ? stored : DEFAULT_THEME
  })

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove('light', 'dark')
    root.classList.add(theme)
    window.localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  const toggle = useCallback(() => {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  return [theme, toggle]
}

function ReyLogo() {
  return (
    <svg viewBox="0 0 40 40" width={40} height={40} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="reyOuter" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#00c2e0" />
          <stop offset="100%" stopColor="#0077b6" />
        </linearGradient>
        <linearGradient id="reyInner" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#05e8a4" />
          <stop offset="100%" stopColor="#00916e" />
        </linearGradient>
        <filter id="reyGlow">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      <rect x="2" y="2" width="36" height="36" rx="9" fill="url(#reyOuter)" />
      <polygon points="20,8 30,20 20,32 10,20" fill="white" opacity="0.92" filter="url(#reyGlow)" />
      <polygon points="20,13 25,20 20,27 15,20" fill="url(#reyInner)" />
      <polygon points="14,17 18,18 17,21" fill="white" opacity="0.5" />
    </svg>
  )
}

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  )
}

function App() {
  const [status, setStatus] = useState<DashboardStatus | null>(null)
  const [watchlistEntries, setWatchlistEntries] = useState<WatchlistEntry[]>([])
  const [connection, setConnection] = useState<Connection>('initial')
  const [tab, setTab] = useState<Tab>('overview')
  const [theme, toggleTheme] = useTheme()

  const offlineTimer = useRef<number | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const wsRetry = useRef<number>(INITIAL_RETRY_MS)
  const mounted = useRef(true)
  const firstLoadStartedAt = useRef<number>(Date.now())

  const refreshWatchlist = useCallback(() => {
    getWatchlist()
      .then(w => setWatchlistIfChanged(setWatchlistEntries, w))
      .catch(() => {/* background refresh */})
  }, [])

  // REST polling: keep retrying with backoff. Never flips to offline until
  // OFFLINE_GRACE_MS has passed without a single success.
  useEffect(() => {
    mounted.current = true
    firstLoadStartedAt.current = Date.now()
    let retryDelay = INITIAL_RETRY_MS
    let timer: number | null = null

    const fetchOnce = async () => {
      if (!mounted.current) return
      try {
        const [s, w] = await Promise.all([getStatus(), getWatchlist()])
        if (!mounted.current) return
        setStatusIfChanged(setStatus, s)
        setWatchlistIfChanged(setWatchlistEntries, w)
        retryDelay = REST_STEADY_POLL_MS
        if (offlineTimer.current) {
          window.clearTimeout(offlineTimer.current)
          offlineTimer.current = null
        }
        setConnection(prev => (prev === 'live' ? 'live' : 'connecting'))
      } catch {
        if (!mounted.current) return
        // Schedule an offline flip if we've never seen data yet.
        if (offlineTimer.current === null && status === null) {
          const elapsed = Date.now() - firstLoadStartedAt.current
          offlineTimer.current = window.setTimeout(() => {
            if (mounted.current && status === null) setConnection('offline')
          }, Math.max(0, OFFLINE_GRACE_MS - elapsed))
        }
        retryDelay = Math.min(retryDelay * 1.6, MAX_RETRY_MS)
      } finally {
        if (mounted.current) {
          timer = window.setTimeout(fetchOnce, retryDelay)
        }
      }
    }

    fetchOnce()
    return () => {
      mounted.current = false
      if (timer) window.clearTimeout(timer)
      if (offlineTimer.current) window.clearTimeout(offlineTimer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // WebSocket with auto-reconnect (back-off identical to REST loop).
  useEffect(() => {
    let reconnectTimer: number | null = null
    let cancelled = false

    const open = () => {
      if (cancelled) return
      try {
        wsRef.current = subscribeToLiveUpdates(
          (newStatus, wl) => {
            setStatusIfChanged(setStatus, newStatus)
            if (wl && wl.length > 0) setWatchlistIfChanged(setWatchlistEntries, wl)
            setConnection('live')
            wsRetry.current = INITIAL_RETRY_MS
            if (offlineTimer.current) {
              window.clearTimeout(offlineTimer.current)
              offlineTimer.current = null
            }
          },
          () => {
            // Drop back to "connecting" — REST polling still drives data.
            setConnection(prev => (prev === 'offline' ? 'offline' : 'connecting'))
            scheduleReconnect()
          },
        )
        if (wsRef.current) {
          wsRef.current.addEventListener('close', () => {
            setConnection(prev => (prev === 'offline' ? 'offline' : 'connecting'))
            scheduleReconnect()
          })
        }
      } catch {
        scheduleReconnect()
      }
    }

    const scheduleReconnect = () => {
      if (cancelled || reconnectTimer != null) return
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        wsRetry.current = Math.min(wsRetry.current * 1.6, MAX_RETRY_MS)
        open()
      }, wsRetry.current)
    }

    open()
    return () => {
      cancelled = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) wsRef.current.close()
    }
  }, [])

  const showProgressBar = connection === 'initial' || connection === 'connecting'
  const showOfflineBanner = connection === 'offline' && status === null

  const dotClass =
    connection === 'live' ? 'connected'
    : connection === 'offline' ? 'disconnected'
    : 'connecting'

  const statusLabel =
    connection === 'live' ? 'Live'
    : connection === 'offline' ? 'Offline'
    : 'Connecting…'

  return (
    <div className="app">
      {showProgressBar && <div className="top-progress" aria-hidden="true" />}

      <div className="header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <ReyLogo />
          <div>
            <h1 style={{ margin: 0 }}>Rey Capital · TradingAgents</h1>
            <p style={{
              color: 'var(--color-text-muted)',
              marginTop: 3,
              fontSize: '0.82rem',
              letterSpacing: '0.02em',
            }}>
              Multi-Agent MT5 Trading Intelligence · Real-time Dashboard
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div className="status-indicator">
            <div className={`status-dot ${dotClass}`}></div>
            <span>{statusLabel}</span>
            {status && (() => {
              const isDemo = (status.account.server ?? '').toLowerCase().includes('demo')
              return (
                <span
                  className={`trading-mode-badge ${isDemo ? 'demo' : 'real'}`}
                  title={status.account.server ?? undefined}
                >
                  {isDemo ? 'DEMO' : 'REAL'}
                </span>
              )
            })()}
          </div>
          <button
            type="button"
            onClick={toggleTheme}
            className="icon-btn"
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            style={{ color: theme === 'dark' ? 'var(--color-gold)' : 'var(--color-info)' }}
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </div>

      {showOfflineBanner && (
        <div className="alert-banner">
          ⚠️ Can't reach the dashboard API. Make sure the backend is running on
          {' '}<code>localhost:8000</code>. Retrying in the background.
        </div>
      )}

      <TabStrip current={tab} onChange={setTab} />

      {tab === 'overview' && (
        status ? (
          <Dashboard
            status={status}
            watchlistEntries={watchlistEntries}
            onWatchlistRefresh={refreshWatchlist}
          />
        ) : (
          <DashboardSkeleton />
        )
      )}
      {tab === 'flow' && <AnalysisFlowPanel />}
      {tab === 'scoreboard' && <ScoreboardPanel />}
      {tab === 'decisions' && <DecisionsLedger />}
      {tab === 'proposals' && <ProposalsPanel />}
      {tab === 'params' && <LearnedParamsPanel />}
    </div>
  )
}

function TabStrip({ current, onChange }: { current: Tab; onChange: (t: Tab) => void }) {
  const tabs: { key: Tab; label: string }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'flow', label: 'Flow' },
    { key: 'scoreboard', label: 'Scoreboard' },
    { key: 'decisions', label: 'Decisions' },
    { key: 'proposals', label: 'Proposals' },
    { key: 'params', label: 'Settings' },
  ]
  return (
    <div className="tab-strip">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`tab-button ${current === t.key ? 'active' : ''}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

export default App
