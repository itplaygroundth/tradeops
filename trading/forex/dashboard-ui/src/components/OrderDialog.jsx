import { useState } from 'react'

function symLabel(s = '') { return s.replace(/m$/i, '') }
function priceDigits(symbol = '') {
  if (/JPY/i.test(symbol)) return 3
  if (/XAU|GOLD/i.test(symbol)) return 3
  return 5
}
function fmt(v, digits = 5) {
  return typeof v === 'number' ? v.toFixed(digits) : '—'
}
function sideOf(p) {
  if (p.type === 0 || p.type === 'BUY') return 'BUY'
  if (p.type === 1 || p.type === 'SELL') return 'SELL'
  return String(p.type || '').toUpperCase()
}

export default function OrderDialog({ position, onClose, onDone }) {
  const digits = priceDigits(position.symbol)
  const side = sideOf(position)
  const [sl, setSl] = useState(position.sl ? String(position.sl) : '')
  const [tp, setTp] = useState(position.tp ? String(position.tp) : '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [confirmClose, setConfirmClose] = useState(false)

  async function post(path, body) {
    setBusy(true); setErr(null)
    try {
      const r = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await r.json().catch(() => ({}))
      if (!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`)
      onDone?.()
      onClose?.()
    } catch (e) {
      setErr(`${symLabel(position.symbol)} #${position.ticket}: ${e.message}`)
      setBusy(false)
    }
  }

  const setSLTP = () => post('/api/mt5/position/modify', {
    ticket: position.ticket,
    sl: sl ? parseFloat(sl) : 0,
    tp: tp ? parseFloat(tp) : 0,
  })

  const closePosition = () => {
    if (!confirmClose) { setConfirmClose(true); return }
    post('/api/mt5/position/close', { ticket: position.ticket })
  }

  return (
    <div className="order-dialog-overlay" onClick={onClose}>
      <div className="order-dialog" onClick={e => e.stopPropagation()}>
        <div className="od-header">
          <span className="od-symbol">{symLabel(position.symbol)}</span>
          <span className={`od-side ${side === 'BUY' ? 'od-buy' : 'od-sell'}`}>{side}</span>
          <span className="od-ticket">#{position.ticket}</span>
        </div>

        <div className="od-grid">
          <div><label>Lots</label><span>{position.volume}</span></div>
          <div><label>Open</label><span>{fmt(position.price_open, digits)}</span></div>
          <div><label>Bid</label><span>{fmt(position.bid, digits)}</span></div>
          <div><label>Ask</label><span>{fmt(position.ask, digits)}</span></div>
          <div>
            <label>P&amp;L</label>
            <span className={position.profit >= 0 ? 'od-profit' : 'od-loss'}>
              {position.profit >= 0 ? '+' : ''}{fmt(position.profit, 2)}
            </span>
          </div>
          <div><label>Current SL</label><span>{position.sl ? fmt(position.sl, digits) : '—'}</span></div>
          <div><label>Current TP</label><span>{position.tp ? fmt(position.tp, digits) : '—'}</span></div>
        </div>

        <div className="od-inputs">
          <label>
            SL price
            <input type="number" step="any" value={sl} onChange={e => setSl(e.target.value)} placeholder="0 = none" />
          </label>
          <label>
            TP price
            <input type="number" step="any" value={tp} onChange={e => setTp(e.target.value)} placeholder="0 = none" />
          </label>
        </div>

        {err && <div className="od-error" role="alert">{err}</div>}

        <div className="od-actions">
          <button className="od-btn od-cancel" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="od-btn od-primary" onClick={setSLTP} disabled={busy}>Set SL/TP</button>
          <button
            className={`od-btn ${confirmClose ? 'od-confirm' : 'od-danger'}`}
            onClick={closePosition}
            disabled={busy}
          >
            {confirmClose ? 'Confirm Close' : 'Close Position'}
          </button>
        </div>
      </div>
    </div>
  )
}
