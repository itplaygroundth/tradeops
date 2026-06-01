import { useState, useEffect } from 'react'

const EXCHANGES = ['binance', 'bybit']

export default function Header({ summary }) {
  const [exchange, setExchange] = useState(summary?.exchange || 'binance')
  const [mode, setMode] = useState(summary?.mode || 'paper')

  // Keep local state in sync with backend snapshot
  useEffect(() => {
    if (summary?.exchange) setExchange(summary.exchange)
    if (summary?.mode) setMode(summary.mode)
  }, [summary?.exchange, summary?.mode])

  // Pull mode from dedicated endpoint once (authoritative paper/live badge)
  useEffect(() => {
    fetch('/api/mode')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.mode) setMode(d.mode) })
      .catch(() => {})
  }, [])

  if (!summary) return null

  const pnl = summary.total_pnl_pct || 0
  const equity = summary.total_equity || 0
  const trades = summary.total_trades || 0
  const winners = summary.winners || 0
  const losers = summary.losers || 0
  const secs = summary.uptime_seconds || 0
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = Math.floor(secs % 60)

  async function switchExchange(ex) {
    if (ex === exchange) return
    setExchange(ex)
    try {
      await fetch('/api/exchange', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exchange: ex }),
      })
    } catch { /* backend may be offline */ }
  }

  return (
    <div className="header">
      <div className="header-left">
        <div className="logo">
          <img src="/fox_logo.jpg" alt="Fox" className="fox-icon" />
          <div className="logo-text">
            <div>
              <span className="logo-ai">Ai</span> <span className="logo-trade">เทรด</span> <span className="logo-deo">..เด้อ</span>
            </div>
            <div className="logo-subtext">CRYPTO</div>
          </div>
        </div>
        <div className="header-stats">
          <Stat label="Total PnL" value={`${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%`} up={pnl >= 0} />
          <Stat label="Equity" value={`${equity.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})} USDT`} />
          <Stat label="Trades" value={trades.toLocaleString()} />
          <Stat label="Win/Loss" value={`${winners}/${losers}`} />
        </div>
      </div>

      <div className="header-right">
        <div className="exchange-switcher">
          {EXCHANGES.map(ex => (
            <button
              key={ex}
              className={`exchange-btn ${exchange === ex ? 'active' : ''}`}
              onClick={() => switchExchange(ex)}
            >
              {ex.toUpperCase()}
            </button>
          ))}
        </div>
        <span className={`mode-badge ${mode === 'live' ? 'mode-live' : 'mode-paper'}`}>
          {mode === 'live' ? '🔴 LIVE' : '🟡 PAPER'}
        </span>
        <div className="uptime">{String(h).padStart(2,'0')}:{String(m).padStart(2,'0')}:{String(s).padStart(2,'0')}</div>
      </div>
    </div>
  )
}

function Stat({ label, value, up }) {
  const cls = up !== undefined ? (up ? 'up' : 'down') : ''
  return (
    <div className="stat-item">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${cls}`}>{value}</div>
    </div>
  )
}
