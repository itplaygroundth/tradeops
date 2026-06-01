import { useState } from 'react'
import { symLabel } from '../lib/crypto.js'

export default function PairManager({ open, onClose, pairs = [], onChange }) {
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  if (!open) return null

  function normalize(s) {
    let v = s.trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
    if (!v) return ''
    if (!/USDT$/.test(v)) v += 'USDT'
    return v
  }

  async function addPair() {
    const pair = normalize(input)
    if (!pair) return
    if (pairs.includes(pair)) { setInput(''); return }
    setBusy(true); setErr(null)
    try {
      const r = await fetch('/api/pairs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pair }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      onChange?.([...pairs, pair])
      setInput('')
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function removePair(pair) {
    setBusy(true); setErr(null)
    try {
      const r = await fetch('/api/pairs', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pair }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      onChange?.(pairs.filter(p => p !== pair))
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pm-overlay" onClick={onClose}>
      <div className="pm-modal" onClick={e => e.stopPropagation()}>
        <div className="pm-header">
          <span>⚙️ Manage Pairs</span>
          <button className="pm-close" onClick={onClose}>✕</button>
        </div>

        <div className="pm-add">
          <input
            placeholder="e.g. DOGE or DOGEUSDT"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') addPair() }}
            disabled={busy}
          />
          <button onClick={addPair} disabled={busy || !input.trim()}>Add</button>
        </div>

        {err && <div className="pm-err">{err}</div>}

        <div className="pm-list">
          {pairs.length === 0 ? (
            <div className="empty-state">No pairs configured</div>
          ) : (
            pairs.map(p => (
              <div className="pm-row" key={p}>
                <span className="pm-sym">{symLabel(p)}</span>
                <span className="pm-full">{p}</span>
                <button className="pm-remove" onClick={() => removePair(p)} disabled={busy}>Remove</button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
