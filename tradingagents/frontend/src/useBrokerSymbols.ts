/**
 * Process-wide broker symbol catalog.
 *
 * The /api/symbols endpoint returns 2500+ symbols; we want to fetch it once
 * and share the result across every component that needs an autocomplete
 * source. Subscribers re-render when the catalog finishes loading.
 *
 * Strategy:
 * - One in-memory cache for the lifetime of the tab.
 * - sessionStorage backup so a hot reload doesn't re-fetch.
 * - Background refresh logic available via `refresh()` from the hook.
 */
import { useEffect, useState } from 'react'
import type { BrokerSymbol, BrokerSymbolsResponse } from './types'
import { getBrokerSymbols } from './api'

const STORAGE_KEY = 'tradingagents.broker.symbols.v1'

interface SymbolState {
  loading: boolean
  symbols: BrokerSymbol[]
  categories: Record<string, number>
  error: string | null
  loadedAt: number | null
}

let cache: SymbolState = readSession()
const subscribers = new Set<(s: SymbolState) => void>()
let inflight: Promise<void> | null = null

function readSession(): SymbolState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return { loading: false, symbols: [], categories: {}, error: null, loadedAt: null }
    const parsed = JSON.parse(raw) as BrokerSymbolsResponse & { loadedAt: number }
    return {
      loading: false,
      symbols: parsed.symbols,
      categories: parsed.categories,
      error: null,
      loadedAt: parsed.loadedAt,
    }
  } catch {
    return { loading: false, symbols: [], categories: {}, error: null, loadedAt: null }
  }
}

function writeSession(payload: BrokerSymbolsResponse) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...payload, loadedAt: Date.now() }))
  } catch {
    // Storage may be full or disabled — non-fatal, the in-memory cache still works.
  }
}

function notify() {
  subscribers.forEach(fn => fn(cache))
}

function load(forceRefresh = false): Promise<void> {
  if (inflight) return inflight
  if (!forceRefresh && cache.symbols.length > 0) return Promise.resolve()
  cache = { ...cache, loading: true, error: null }
  notify()
  inflight = getBrokerSymbols(forceRefresh)
    .then(payload => {
      cache = {
        loading: false,
        symbols: payload.symbols,
        categories: payload.categories,
        error: null,
        loadedAt: Date.now(),
      }
      writeSession(payload)
      notify()
    })
    .catch(err => {
      cache = { ...cache, loading: false, error: String(err) }
      notify()
    })
    .finally(() => {
      inflight = null
    })
  return inflight
}

export function useBrokerSymbols() {
  const [state, setState] = useState<SymbolState>(cache)

  useEffect(() => {
    subscribers.add(setState)
    // Kick off a fetch if nothing has loaded yet
    if (cache.symbols.length === 0 && !cache.loading) load(false)
    // If the session cache is older than 30 minutes, refresh in the background
    else if (cache.loadedAt && Date.now() - cache.loadedAt > 30 * 60_000) load(true)
    return () => {
      subscribers.delete(setState)
    }
  }, [])

  return {
    ...state,
    refresh: () => load(true),
  }
}
