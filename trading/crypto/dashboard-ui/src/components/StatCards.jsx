import { fmtUsdt } from '../lib/crypto.js'

export default function StatCards({ summary, agents = [], positions = [] }) {
  if (!summary) return null

  const pnlPct = summary.total_pnl_pct || 0
  const equity = summary.total_equity || 0
  const trades = summary.total_trades || 0
  const winners = summary.winners || 0
  const losers = summary.losers || 0
  const openPositions = summary.open_positions ?? positions.length
  const winRate = trades > 0 ? (winners / trades) * 100 : 0

  const activeAgents = (agents || []).filter(a => a.in_trade).length
  const totalAgents = (agents || []).length

  // Net P&L across open positions (USDT)
  const netPos = positions.reduce((s, p) => s + (p.profit || 0), 0)

  return (
    <div className="stat-cards-row">

      {/* ═══ Total PnL ═══ */}
      <div className="stat-card today-pnl">
        <div className="stat-card-label">Total PnL</div>
        <div className="stat-card-value">
          <span className={pnlPct >= 0 ? 'up' : 'down'}>
            {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}
          </span>
          <span className="stat-card-currency">%</span>
        </div>
        <div className="stat-card-breakdown">
          <span className="breakdown-item">
            <span className="breakdown-dot profit"></span>
            WIN <strong>{winners}</strong>
          </span>
          <span className="breakdown-item">
            <span className="breakdown-dot loss"></span>
            LOSS <strong>{losers}</strong>
          </span>
          <span className="breakdown-item muted">
            TRADES <strong>{trades}</strong>
          </span>
        </div>
      </div>

      {/* ═══ Performance ═══ */}
      <div className="stat-card monthly-pnl">
        <div className="stat-card-label">Performance</div>
        <div className="perf-metrics">
          <div className="perf-row">
            <span className="perf-label">Win Rate</span>
            <span className={`perf-value ${winRate >= 50 ? 'up' : 'down'}`}>{winRate.toFixed(1)}%</span>
          </div>
          <div className="perf-row">
            <span className="perf-label">Equity</span>
            <span className="perf-value">{fmtUsdt(equity)} USDT</span>
          </div>
          <div className="perf-row">
            <span className="perf-label">Exchange</span>
            <span className="perf-value">{(summary.exchange || '—').toUpperCase()}</span>
          </div>
        </div>
      </div>

      {/* ═══ Open Positions ═══ */}
      <div className="stat-card positions">
        <div className="pos-head">
          <span className="stat-card-label">Open Positions</span>
          <span className="pos-open-count">{openPositions} open</span>
        </div>
        <div className={`pos-net ${netPos >= 0 ? 'up' : 'down'}`}>
          {netPos >= 0 ? '+' : ''}{fmtUsdt(netPos)} USDT
          <span className="pos-net-label">net P&L</span>
        </div>
        {positions.length > 0 && (
          <div className="pos-live">
            {positions.slice(0, 3).map(pos => (
              <div key={pos.ticket} className="pos-live-row">
                <span className="pos-live-sym">
                  {(pos.symbol || '').replace(/USDT$/i, '')}
                  <span className={pos.type === 'BUY' ? 'up' : 'down'}> {pos.type}</span>
                </span>
                <span className={`pos-live-pnl ${pos.profit >= 0 ? 'up' : 'down'}`}>
                  {pos.profit >= 0 ? '+' : ''}{fmtUsdt(pos.profit)}
                </span>
              </div>
            ))}
            {positions.length > 3 && (
              <div className="pos-live-more">+{positions.length - 3} more</div>
            )}
          </div>
        )}
      </div>

      {/* ═══ Agent Status ═══ */}
      <div className="stat-card dca-top-card">
        <div className="stat-card-label">Agent Status</div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 5 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 8, color: 'var(--text-muted)', marginBottom: 1 }}>🤖 In Trade</div>
            <strong style={{ fontSize: 15, color: 'var(--gold)', fontFamily: "'JetBrains Mono', monospace" }}>
              {activeAgents}
            </strong>
            <span style={{ fontSize: 9, color: 'var(--text-muted)' }}> / {totalAgents}</span>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 8, color: 'var(--text-muted)', marginBottom: 1 }}>🎯 Win Rate</div>
            <strong style={{ fontSize: 15, fontFamily: "'JetBrains Mono', monospace", color: winRate >= 50 ? 'var(--green)' : 'var(--red)' }}>
              {winRate.toFixed(1)}%
            </strong>
          </div>
        </div>
        <div className="stat-card-footer">
          <span>MODE <strong>{(summary.mode || 'paper').toUpperCase()}</strong></span>
          <span>EQUITY <strong>{fmtUsdt(equity)}</strong></span>
        </div>
      </div>
    </div>
  )
}
