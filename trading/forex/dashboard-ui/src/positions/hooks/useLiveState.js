import { useState, useEffect, useCallback } from 'react'

export function useLiveState(intervalMs = 5000) {
  const [data, setData] = useState(null)
  const [ts, setTs] = useState('')

  const fetchData = useCallback(async () => {
    try {
      const r = await fetch('live_state.json?t=' + Date.now())
      if (r.ok) {
        setData(await r.json())
        setTs(new Date().toLocaleTimeString('th-TH'))
      }
    } catch {}
  }, [])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, intervalMs)
    return () => clearInterval(id)
  }, [fetchData, intervalMs])

  return { data, ts }
}
