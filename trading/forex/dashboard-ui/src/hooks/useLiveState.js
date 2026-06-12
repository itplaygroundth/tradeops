import { useState, useEffect, useCallback } from 'react'

export function useLiveState() {
  const [state, setState] = useState(null)
  const [error, setError] = useState(null)
  const [mt5, setMt5] = useState(null)
  const [manualActions, setManualActions] = useState([])

  const fetchState = useCallback(async () => {
    try {
      const resp = await fetch('/live_state.json?_=' + Date.now())
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      setState(data)
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  const fetchMT5 = useCallback(async () => {
    try {
      const [acctRes, posRes] = await Promise.all([
        fetch('/api/mt5/account'),
        fetch('/api/mt5/positions')
      ])
      const acct = await acctRes.json()
      const pos = await posRes.json()
      const ok = acctRes.ok && posRes.ok && !acct.error && !pos.error
      setMt5({
        account: acct,
        positions: pos.positions ?? [],
        status: acct.mt5_status ?? (ok ? 'online' : 'offline'),
        cachedAt: acct.cached_at,
      })
    } catch {
      setMt5(prev => prev ? { ...prev, status: 'offline' } : { account: null, positions: [], status: 'offline', cachedAt: null })
    }
  }, [])

  const fetchManualActions = useCallback(async () => {
    try {
      const resp = await fetch('/api/manual_actions?limit=50')
      const data = await resp.json()
      setManualActions(data.items ?? [])
    } catch {
      setManualActions([])
    }
  }, [])

  useEffect(() => {
    fetchState()
    fetchMT5()
    fetchManualActions()
    const id1 = setInterval(fetchState, 2000)
    const id2 = setInterval(fetchMT5, 5000)
    const id3 = setInterval(fetchManualActions, 10000)
    return () => { clearInterval(id1); clearInterval(id2); clearInterval(id3) }
  }, [fetchState, fetchMT5, fetchManualActions])

  return { state, error, mt5, manualActions, refreshMT5: fetchMT5, refreshManualActions: fetchManualActions }
}
