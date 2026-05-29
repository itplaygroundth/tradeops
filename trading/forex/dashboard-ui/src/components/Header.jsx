import { useState } from 'react'

export default function Header({ summary }) {
  if (!summary) return null

  // Deployment enforces live-only; show static badge
  const [mode] = useState('live')

  const pnl = summary.total_pnl_pct || 0
  const equity = summary.total_equity || 0
  const trades = summary.total_trades || 0
  const winners = summary.winners || 0
  const losers = summary.losers || 0
  const secs = summary.uptime_seconds || 0
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = Math.floor(secs % 60)
  const regime = summary.regime?.current_regime || ''

  const regimeColors = {
    TRENDING: '#5e5ce6',
    SIDEWAYS: '#ff9f0a',
    HIGH_VOL: '#ff453a',
    BEARISH: '#ff453a',
    BULLISH: '#30d158',
    MIXED: '#8e8e93',
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
            <div className="logo-subtext">forex</div>
          </div>
        </div>
        <div className="header-stats">
          <Stat label="Total PnL" value={`${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%`} up={pnl >= 0} />
          <Stat label="Equity" value={`$${equity.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`} />
          <Stat label="Trades" value={trades.toLocaleString()} />
          <Stat label="Win/Loss" value={`${winners}/${losers}`} />
        </div>
      </div>

      <div className="header-right">
        {regime && (
          <span className="hm-regime" style={{ background: regimeColors[regime] || '#555' }}>
            {regime}
          </span>
        )}
        <span className="mode-badge" title="Live-only deployment">{mode === 'live' ? '🔴 LIVE' : '🟡 PAPER'}</span>
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
