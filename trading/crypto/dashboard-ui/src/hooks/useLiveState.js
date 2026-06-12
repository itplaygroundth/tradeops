import { useState, useEffect, useCallback } from 'react'

export function useLiveState() {
  const [state, setState] = useState(null)
  const [error, setError] = useState(null)
  const [account, setAccount] = useState(null)
  const [positions, setPositions] = useState([])

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

  const fetchAccount = useCallback(async () => {
    try {
      const [acctRes, posRes] = await Promise.all([
        fetch('/api/account'),
        fetch('/api/positions'),
      ])
      const acct = acctRes.ok ? await acctRes.json() : null
      const pos = posRes.ok ? await posRes.json() : { positions: [] }
      setAccount(acct)
      setPositions(pos.positions ?? [])
    } catch {
      // leave previous values on transient failure
    }
  }, [])

  useEffect(() => {
    fetchState()
    fetchAccount()
    const id1 = setInterval(fetchState, 2000)
    const id2 = setInterval(fetchAccount, 5000)
    return () => { clearInterval(id1); clearInterval(id2) }
  }, [fetchState, fetchAccount])

  return { state, error, account, positions }
}
