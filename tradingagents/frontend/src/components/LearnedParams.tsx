import { useEffect, useMemo, useState } from 'react'
import type { AppSettings, Goals, LearnedParams, WatchlistEntry } from '../types'
import {
  getGoals, getLearnedParams, getSettings, updateSettings,
  getWatchlist, addManyToWatchlist, removeFromWatchlist,
} from '../api'
import { useBrokerSymbols } from '../useBrokerSymbols'

export function LearnedParamsPanel() {
  const [params, setParams] = useState<LearnedParams | null>(null)
  const [goals, setGoals] = useState<Goals | null>(null)
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setError(null)
    Promise.all([getLearnedParams(), getGoals(), getSettings(), getWatchlist()])
      .then(([p, g, s, w]) => {
        setParams(p)
        setGoals(g)
        setSettings(s.settings)
        setOllamaModels(s.ollama_models || [])
        setWatchlist(w)
      })
      .catch((e) => setError(String(e)))
  }, [])

  const refreshWatchlist = () => {
    getWatchlist().then(setWatchlist).catch((e) => setError(String(e)))
  }

  if (error) return (
    <div className="card alert-banner" style={{ margin: 0 }}>
      ⚠️ Couldn't load settings. Retrying — keep this tab open.
    </div>
  )
  if (!params || !goals || !settings) return (
    <div style={{ display: 'grid', gap: 20 }}>
      <div className="card">
        <div className="skeleton skeleton-line sm" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16, marginTop: 16 }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i}>
              <div className="skeleton skeleton-line sm" />
              <div className="skeleton skeleton-line" style={{ marginTop: 6 }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  function patch<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setSettings(current => current ? { ...current, [key]: value } : current)
  }

  async function save() {
    if (!settings) return
    setSaving(true)
    setError(null)
    try {
      const result = await updateSettings(settings)
      setSettings(result.settings)
      setOllamaModels(result.ollama_models || ollamaModels)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ display: 'grid', gap: 20 }}>

      {/* ── Mock Mode Banner ─────────────────────────────────────────── */}
      {settings && false && <div style={{
        padding: '16px 20px',
        borderRadius: 'var(--radius)',
        border: `2px solid ${settings?.mock_mode_enabled ? 'var(--color-warning)' : 'var(--color-border)'}`,
        background: settings?.mock_mode_enabled
          ? 'color-mix(in srgb, var(--color-warning) 10%, var(--color-surface))'
          : 'var(--color-surface)',
        display: 'flex',
        alignItems: 'center',
        gap: 20,
        flexWrap: 'wrap',
      }}>
        <div style={{ flex: 1, minWidth: 220 }}>
          <div style={{
            fontWeight: 700,
            fontSize: '1rem',
            color: settings?.mock_mode_enabled ? 'var(--color-warning)' : 'var(--color-text)',
            marginBottom: 4,
          }}>
            {settings?.mock_mode_enabled ? '⚡ Mock Mode ON' : 'Mock Mode OFF'}
          </div>
          <div style={{ fontSize: '0.82rem', color: 'var(--color-text-muted)', lineHeight: 1.5 }}>
            {settings?.mock_mode_enabled
              ? 'Scheduled analyses skip the LLM pipeline — a random BUY or SELL is picked and sent directly to MT5. Scoreboard, Decisions, and executions all update normally.'
              : 'Real mode: scheduled analyses run the full LLM pipeline before placing any trade.'}
          </div>
        </div>
        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          cursor: 'pointer',
          userSelect: 'none',
          fontSize: '0.9rem',
          fontWeight: 600,
          color: settings?.mock_mode_enabled ? 'var(--color-warning)' : 'var(--color-text-muted)',
        }}>
          <input
            type="checkbox"
            checked={settings!.mock_mode_enabled}
            onChange={e => patch('mock_mode_enabled', e.target.checked)}
            style={{ width: 18, height: 18, cursor: 'pointer' }}
          />
          {settings!.mock_mode_enabled ? 'Enabled' : 'Disabled'}
        </label>
        <button
          onClick={save}
          disabled={saving}
          className="btn"
          style={{
            background: settings!.mock_mode_enabled ? 'var(--color-warning)' : undefined,
            color: settings!.mock_mode_enabled ? '#000' : undefined,
          }}
        >
          {saving ? 'Saving…' : 'Apply'}
        </button>
      </div>}
      {/* ─────────────────────────────────────────────────────────────── */}

      <div className="card">
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          gap: 16,
          alignItems: 'center',
          marginBottom: 8,
        }}>
          <div className="card-title" style={{ marginBottom: 0 }}>Settings</div>
          <button onClick={save} disabled={saving} className="btn">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>

        <datalist id="ollama-models">
          {ollamaModels.map(model => <option key={model} value={model} />)}
        </datalist>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          gap: 16,
          marginTop: 16,
        }}>
          <Field label="LLM Provider">
            <TextInput value={settings.llm_provider} onChange={v => patch('llm_provider', v)} />
          </Field>
          <Field label="Fallback Provider">
            <TextInput value={settings.fallback_llm_provider} onChange={v => patch('fallback_llm_provider', v)} />
          </Field>
          <Field label="Quick Model">
            <ModelInput value={settings.quick_think_llm} onChange={v => patch('quick_think_llm', v)} />
          </Field>
          <Field label="Deep Model">
            <ModelInput value={settings.deep_think_llm} onChange={v => patch('deep_think_llm', v)} />
          </Field>
          <CheckboxRow
            label={`Premium deep model (${settings.premium_deep_llm || 'kimi-k3:cloud'}) — needs Ollama Pro/Max`}
            checked={settings.premium_deep_enabled}
            onChange={v => patch('premium_deep_enabled', v)}
          />
          <Field label="Premium Deep Model">
            <ModelInput value={settings.premium_deep_llm} onChange={v => patch('premium_deep_llm', v)} />
          </Field>
          <Field label="Fallback Quick Model">
            <ModelInput value={settings.fallback_quick_think_llm} onChange={v => patch('fallback_quick_think_llm', v)} />
          </Field>
          <Field label="Fallback Deep Model">
            <ModelInput value={settings.fallback_deep_think_llm} onChange={v => patch('fallback_deep_think_llm', v)} />
          </Field>
          <CheckboxRow
            label="Enable fallback"
            checked={settings.llm_fallback_enabled}
            onChange={v => patch('llm_fallback_enabled', v)}
          />
          <CheckboxRow
            label="Prefer fallback"
            checked={settings.llm_prefer_fallback}
            onChange={v => patch('llm_prefer_fallback', v)}
          />
          <Field label="Watchlist Check Seconds">
            <NumberInput
              value={settings.watchlist_check_interval_seconds}
              min={10}
              onChange={v => patch('watchlist_check_interval_seconds', v)}
            />
          </Field>
          <Field label="Trade Comment">
            <TextInput value={settings.trade_comment} onChange={v => patch('trade_comment', v)} />
          </Field>
          <CheckboxRow
            label="Auto trade enabled"
            checked={settings.auto_trade_enabled}
            onChange={v => patch('auto_trade_enabled', v)}
          />
          <CheckboxRow
            label="Demo/paper only"
            checked={settings.auto_trade_paper_only}
            onChange={v => patch('auto_trade_paper_only', v)}
          />
          {settings && false && <CheckboxRow
            label="Mock mode (skip LLM)"
            checked={settings!.mock_mode_enabled}
            onChange={v => patch('mock_mode_enabled', v)}
          />}
          <Field label="Max Risk Per Trade %">
            <NumberInput
              value={settings.max_risk_per_trade_percent}
              min={0.01}
              step={0.01}
              onChange={v => patch('max_risk_per_trade_percent', v)}
            />
          </Field>
          <Field label="Max Risk Per Trade USD">
            <NullableNumberInput
              value={settings.max_risk_per_trade_usd}
              min={0}
              onChange={v => patch('max_risk_per_trade_usd', v)}
            />
          </Field>
        </div>

        <div style={{
          color: 'var(--color-text-muted)',
          fontSize: '0.82rem',
          marginTop: 18,
          padding: '10px 14px',
          background: 'var(--color-surface-2)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
        }}>
          <strong style={{ color: 'var(--color-text-dim)' }}>Installed Ollama models:</strong>{' '}
          {ollamaModels.length ? ollamaModels.join(', ') : 'none detected'}
        </div>
      </div>

      <SymbolsCard
        entries={watchlist}
        onChange={refreshWatchlist}
      />

      <div className="card">
        <div className="card-title">Learned params &amp; goals</div>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 20,
          marginTop: 12,
        }}>
          <div>
            <div style={{
              color: 'var(--color-text-muted)',
              fontSize: '0.78rem',
              marginBottom: 8,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              fontWeight: 600,
            }}>
              learned_params.json (mutable)
            </div>
            <KVTable obj={params} />
          </div>
          <div>
            <div style={{
              color: 'var(--color-text-muted)',
              fontSize: '0.78rem',
              marginBottom: 8,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              fontWeight: 600,
            }}>
              goals.json (read-only targets)
            </div>
            <KVTable obj={goals} />
          </div>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'grid', gap: 6 }}>
      <span style={{
        color: 'var(--color-text-muted)',
        fontSize: '0.74rem',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        fontWeight: 600,
      }}>
        {label}
      </span>
      {children}
    </label>
  )
}

function CheckboxRow({
  label,
  checked,
  onChange,
}: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      color: 'var(--color-text)',
      fontSize: '0.9rem',
      padding: '8px 12px',
      background: 'var(--color-surface-2)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-sm)',
      cursor: 'pointer',
    }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
      />
      {label}
    </label>
  )
}

function TextInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <input value={value} onChange={e => onChange(e.target.value)} />
}

function ModelInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <input value={value} list="ollama-models" onChange={e => onChange(e.target.value)} />
}

function NumberInput({
  value,
  min,
  step,
  onChange,
}: {
  value: number
  min: number
  step?: number
  onChange: (value: number) => void
}) {
  return <input type="number" min={min} step={step} value={value} onChange={e => onChange(Number(e.target.value))} />
}

function NullableNumberInput({
  value,
  min,
  onChange,
}: {
  value: number | null
  min: number
  onChange: (value: number | null) => void
}) {
  return (
    <input
      type="number"
      min={min}
      value={value ?? ''}
      onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))}
    />
  )
}

function KVTable({ obj }: { obj: Record<string, unknown> }) {
  const entries = Object.entries(obj)
  if (entries.length === 0) {
    return (
      <div style={{
        color: 'var(--color-text-muted)',
        fontStyle: 'italic',
        padding: 12,
      }}>
        (empty)
      </div>
    )
  }
  return (
    <table className="table">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <td style={{ color: 'var(--color-text-muted)', width: '50%' }}>{k}</td>
            <td style={{
              textAlign: 'right',
              fontFamily: 'ui-monospace, "Geist Mono", monospace',
              color: 'var(--color-primary)',
              fontSize: '0.86rem',
            }}>
              {typeof v === 'object' ? JSON.stringify(v) : String(v)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

interface SymbolsCardProps {
  entries: WatchlistEntry[]
  onChange: () => void
}

function SymbolsCard({ entries, onChange }: SymbolsCardProps) {
  const [bulk, setBulk] = useState('')
  const [interval, setInterval] = useState(1)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<{ added: string[]; failed: { symbol: string; error: string }[] } | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)
  const [picker, setPicker] = useState('')
  const broker = useBrokerSymbols()

  // Lookup index built once per render to validate user-typed symbols.
  const symbolIndex = useMemo(() => {
    const map = new Map<string, { description: string; category: string }>()
    broker.symbols.forEach(s => {
      map.set(s.name, { description: s.description, category: s.category })
    })
    return map
  }, [broker.symbols])

  const parsedPreview = Array.from(new Set(
    bulk
      .split(/[\s,;\n]+/)
      .map(s => s.trim().toUpperCase())
      .filter(Boolean)
  ))

  const unknownInPreview = parsedPreview.filter(s => symbolIndex.size > 0 && !symbolIndex.has(s))

  async function handleBulkAdd(e: React.FormEvent) {
    e.preventDefault()
    if (parsedPreview.length === 0) return
    setBusy(true)
    setStatus(null)
    try {
      const result = await addManyToWatchlist(parsedPreview, interval)
      setStatus(result)
      if (result.added.length > 0) {
        setBulk('')
        onChange()
      }
    } catch (e) {
      setStatus({ added: [], failed: [{ symbol: '(request)', error: String(e) }] })
    } finally {
      setBusy(false)
    }
  }

  async function handleRemove(symbol: string) {
    setRemoving(symbol)
    try {
      await removeFromWatchlist(symbol)
      onChange()
    } finally {
      setRemoving(null)
    }
  }

  function addPickerToBulk() {
    const candidate = picker.trim().toUpperCase()
    if (!candidate) return
    const existing = new Set(parsedPreview)
    if (existing.has(candidate)) return
    setBulk(prev => prev.trim() ? `${prev.trim()}, ${candidate}` : candidate)
    setPicker('')
  }

  // Show top categories so the picker hints at what's available.
  const categoryChips = Object.entries(broker.categories)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)

  return (
    <div className="card">
      <div className="card-title" style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span>Symbols &amp; Watchlist</span>
        <span style={{
          textTransform: 'none',
          letterSpacing: 0,
          fontWeight: 500,
          color: 'var(--color-text-muted)',
          fontSize: '0.72rem',
        }}>
          {broker.loading
            ? 'Loading broker catalog…'
            : broker.symbols.length > 0
            ? `${broker.symbols.length.toLocaleString()} broker symbols available`
            : broker.error
            ? '⚠ broker catalog unavailable'
            : ''}
        </span>
      </div>

      {/* Picker — autocomplete a single broker symbol then push into the bulk list */}
      {broker.symbols.length > 0 && (
        <div style={{
          display: 'flex',
          gap: 8,
          marginBottom: 14,
          flexWrap: 'wrap',
          alignItems: 'center',
        }}>
          <input
            list="broker-symbols-picker"
            value={picker}
            onChange={e => setPicker(e.target.value.toUpperCase())}
            onKeyDown={e => {
              if (e.key === 'Enter') { e.preventDefault(); addPickerToBulk() }
            }}
            placeholder="Search broker symbols (e.g. EURUSD, AAPL)…"
            style={{ flex: 1, minWidth: 240 }}
          />
          <datalist id="broker-symbols-picker">
            {broker.symbols.slice(0, 1500).map(s => (
              <option key={s.name} value={s.name}>
                {s.category} · {s.description}
              </option>
            ))}
          </datalist>
          <button
            type="button"
            onClick={addPickerToBulk}
            disabled={!picker.trim()}
            className="btn btn-ghost"
            style={{ padding: '7px 14px', fontSize: '0.82rem' }}
          >
            ↓ Queue
          </button>
          {categoryChips.length > 0 && (
            <div style={{
              display: 'flex',
              gap: 6,
              flexWrap: 'wrap',
              width: '100%',
              marginTop: 4,
            }}>
              {categoryChips.map(([cat, n]) => (
                <span key={cat} style={{
                  fontSize: '0.7rem',
                  color: 'var(--color-text-muted)',
                  background: 'var(--color-surface-2)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 999,
                  padding: '2px 9px',
                  letterSpacing: '0.04em',
                }}>
                  {cat} · {n}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <form onSubmit={handleBulkAdd} style={{ display: 'grid', gap: 12 }}>
        <label style={{ display: 'grid', gap: 6 }}>
          <span style={{
            color: 'var(--color-text-muted)',
            fontSize: '0.74rem',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontWeight: 600,
          }}>
            Add symbols (comma, space, or newline separated)
          </span>
          <textarea
            value={bulk}
            onChange={e => setBulk(e.target.value.toUpperCase())}
            placeholder="EURUSD, GBPUSD, USDJPY&#10;XAUUSD BTCUSD&#10;NAS100"
            rows={3}
            style={{ width: '100%', minHeight: 70, resize: 'vertical', fontFamily: 'inherit' }}
          />
        </label>

        <div style={{
          display: 'flex',
          gap: 12,
          flexWrap: 'wrap',
          alignItems: 'flex-end',
        }}>
          <label style={{ display: 'grid', gap: 6, minWidth: 180 }}>
            <span style={{
              color: 'var(--color-text-muted)',
              fontSize: '0.74rem',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              fontWeight: 600,
            }}>
              Check interval (minutes)
            </span>
            <input
              type="number"
              min={1}
              value={interval}
              onChange={e => setInterval(Math.max(1, Number(e.target.value) || 1))}
            />
          </label>

          <div style={{ flex: 1, minWidth: 180, color: 'var(--color-text-muted)', fontSize: '0.82rem' }}>
            {parsedPreview.length > 0 ? (
              <>
                <div>
                  <strong style={{ color: 'var(--color-primary)' }}>
                    {parsedPreview.length} symbol{parsedPreview.length === 1 ? '' : 's'}
                  </strong>{' '}
                  ready:{' '}
                  {parsedPreview.map((s, idx) => {
                    const known = symbolIndex.size === 0 || symbolIndex.has(s)
                    return (
                      <span key={s}>
                        <span
                          title={
                            known
                              ? symbolIndex.get(s)?.description ?? s
                              : 'Not found in the broker catalog — the add may fail.'
                          }
                          style={{
                            color: known ? 'var(--color-text)' : 'var(--color-warning)',
                            textDecoration: known ? 'none' : 'underline dotted',
                            fontWeight: known ? 500 : 600,
                          }}
                        >
                          {s}
                        </span>
                        {idx < parsedPreview.length - 1 ? ', ' : ''}
                      </span>
                    )
                  })}
                </div>
                {unknownInPreview.length > 0 && (
                  <div style={{ marginTop: 4, color: 'var(--color-warning)', fontSize: '0.76rem' }}>
                    ⚠ {unknownInPreview.length} not in broker catalog:{' '}
                    {unknownInPreview.join(', ')}
                  </div>
                )}
              </>
            ) : (
              <em>Paste or type symbols above, or use the picker to queue.</em>
            )}
          </div>

          <button
            type="submit"
            disabled={busy || parsedPreview.length === 0}
            className="btn"
          >
            {busy ? 'Adding…' : `+ Add ${parsedPreview.length || ''}`.trim()}
          </button>
        </div>
      </form>

      {status && (
        <div style={{
          marginTop: 14,
          padding: '10px 14px',
          background: status.failed.length === 0
            ? 'var(--color-profit-dim)'
            : 'var(--color-warning-dim)',
          border: `1px solid color-mix(in srgb, ${status.failed.length === 0 ? 'var(--color-profit)' : 'var(--color-warning)'} 40%, transparent 60%)`,
          borderRadius: 'var(--radius-sm)',
          fontSize: '0.85rem',
          color: 'var(--color-text)',
        }}>
          {status.added.length > 0 && (
            <div style={{ color: 'var(--color-profit)' }}>
              ✓ Added {status.added.length}: {status.added.join(', ')}
            </div>
          )}
          {status.failed.length > 0 && (
            <div style={{ color: 'var(--color-warning)', marginTop: status.added.length ? 4 : 0 }}>
              ⚠ Failed {status.failed.length}:{' '}
              {status.failed.map(f => `${f.symbol} (${f.error.slice(0, 60)})`).join('; ')}
            </div>
          )}
        </div>
      )}

      <div style={{
        marginTop: 18,
        paddingTop: 16,
        borderTop: '1px solid var(--color-border)',
      }}>
        <div style={{
          color: 'var(--color-text-muted)',
          fontSize: '0.74rem',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          fontWeight: 600,
          marginBottom: 10,
        }}>
          Currently watched ({entries.length})
        </div>

        {entries.length === 0 ? (
          <div style={{
            color: 'var(--color-text-muted)',
            fontStyle: 'italic',
            padding: 12,
          }}>
            No symbols in watchlist
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {entries.map(e => (
              <div
                key={e.symbol}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '5px 6px 5px 10px',
                  background: 'linear-gradient(135deg, rgb(0 194 224 / 0.18), rgb(0 194 224 / 0.08))',
                  border: '1px solid rgb(0 194 224 / 0.35)',
                  borderRadius: 999,
                  color: 'var(--color-primary)',
                  fontWeight: 700,
                  fontSize: '0.82rem',
                  letterSpacing: '0.04em',
                }}
              >
                {e.symbol}
                <span style={{
                  fontSize: '0.66rem',
                  fontWeight: 500,
                  color: 'var(--color-text-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}>
                  {e.mode} · {e.interval_minutes ? `${e.interval_minutes}m` : `${e.interval_hours}h`}
                </span>
                <button
                  type="button"
                  onClick={() => handleRemove(e.symbol)}
                  disabled={removing === e.symbol}
                  aria-label={`Remove ${e.symbol}`}
                  title={`Remove ${e.symbol}`}
                  style={{
                    width: 22,
                    height: 22,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderRadius: '50%',
                    border: '1px solid color-mix(in srgb, var(--color-loss) 50%, transparent 50%)',
                    background: 'transparent',
                    color: 'var(--color-loss)',
                    cursor: 'pointer',
                    fontSize: '0.75rem',
                    lineHeight: 1,
                    padding: 0,
                  }}
                >
                  {removing === e.symbol ? '…' : '✕'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
