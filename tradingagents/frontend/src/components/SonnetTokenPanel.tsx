import { useEffect, useState } from 'react'
import type { AppSettings, TokenUsage } from '../types'
import { getSettings, updateSettings, resetTokenUsage } from '../api'

interface SonnetTokenPanelProps {
  usage?: TokenUsage | null
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

/**
 * Shows the running LLM token count (across ALL providers/models) and the
 * LLM kill switch. The displayed numbers stay live via the dashboard's 2s
 * status broadcast; the buttons write settings/counter state and let the
 * next poll reconcile. The active model line comes from /api/settings.
 */
export function SonnetTokenPanel({ usage }: SonnetTokenPanelProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [settings, setSettings] = useState<AppSettings | null>(null)

  useEffect(() => {
    getSettings().then(s => setSettings(s.settings)).catch(() => {})
  }, [])

  const deepModel = settings?.premium_deep_enabled
    ? settings.premium_deep_llm
    : settings?.deep_think_llm
  const modelLine = settings
    ? `${settings.llm_provider} · deep: ${deepModel} · quick: ${settings.quick_think_llm}` +
      (settings.premium_deep_enabled ? ' · premium ON' : '')
    : null

  const enabled = usage?.llm_enabled ?? true
  const total = usage?.total ?? 0
  const budget = usage?.budget_max ?? 0
  const pctOfBudget = budget > 0 ? Math.min(100, (total / budget) * 100) : 0
  const overBudget = budget > 0 && total >= budget

  async function toggleSonnet() {
    setBusy(true)
    setError(null)
    try {
      await updateSettings({ llm_enabled: !enabled })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'toggle failed')
    } finally {
      setBusy(false)
    }
  }

  async function resetCounter() {
    setBusy(true)
    setError(null)
    try {
      await resetTokenUsage()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'reset failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="card"
      style={{
        marginBottom: 24,
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        borderLeft: `4px solid ${enabled ? '#3fb950' : '#f85149'}`,
      }}
    >
      <div>
        <div className="card-title">LLM Token Usage</div>
        <div className="card-value" style={{ color: overBudget ? '#f85149' : undefined }}>
          {formatTokens(total)}
        </div>
        <div className="card-subtext">
          ↑ {formatTokens(usage?.tokens_in ?? 0)} in · ↓ {formatTokens(usage?.tokens_out ?? 0)} out
          {' · '}{usage?.llm_calls ?? 0} calls
          {budget > 0
            ? ` · ${pctOfBudget.toFixed(0)}% of ${formatTokens(budget)} budget`
            : ' · no budget cap'}
        </div>
        {modelLine && (
          <div className="card-subtext" style={{ marginTop: 2, fontWeight: 600 }}>
            {modelLine}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span
          style={{
            fontSize: '0.8rem',
            fontWeight: 600,
            color: enabled ? '#3fb950' : '#f85149',
          }}
        >
          {enabled ? 'LLM ACTIVE' : 'LLM STOPPED'}
        </span>
        <button
          onClick={toggleSonnet}
          disabled={busy}
          className={enabled ? 'btn btn-danger' : 'btn btn-trade'}
          style={{ padding: '8px 16px' }}
          title={enabled ? 'Immediately halt all LLM analysis (stops token spend)' : 'Resume LLM analysis'}
        >
          {busy ? '…' : enabled ? 'Stop LLM' : 'Resume LLM'}
        </button>
        <button
          onClick={resetCounter}
          disabled={busy}
          className="btn btn-ghost"
          style={{ padding: '8px 12px' }}
          title="Reset the token counter to zero"
        >
          Reset counter
        </button>
        {error && <span style={{ color: '#f85149', fontSize: '0.76rem' }}>{error}</span>}
      </div>
    </div>
  )
}
