export default function StatCards({ summary, mt5 }) {
  if (!summary) return null

  const pnlPct = summary.total_pnl_pct || 0
  const pnlDollar = summary.total_pnl || 0
  const equity = summary.total_equity || 0
  const trades = summary.total_trades || 0
  const winners = summary.winners || 0
  const losers = summary.losers || 0

  // Paper trade data
  const paperTrade = summary.paper_trade || {}
  const stats = paperTrade.statistics || {}
  const positionsSummary = paperTrade.positions_summary || {}

  // Forex risk stats
  const activeAgents = summary.active_agents || 0
  const totalAgents = summary.total_agents || 25
  const winRate = trades > 0 ? ((winners / trades) * 100) : 0

  return (
    <div className="stat-cards-row">

      {/* ═══ Today PnL ═══ */}
      <div className="stat-card today-pnl">
        <div className="stat-card-label">Total PnL</div>
        <div className="stat-card-value">
          <span className={pnlPct >= 0 ? 'up' : 'down'}>
            {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}
          </span>
          <span className="stat-card-currency">%</span>
          <span className={`stat-card-dollar ${pnlDollar >= 0 ? 'up' : 'down'}`}>
            {pnlDollar >= 0 ? '+' : ''}${pnlDollar.toFixed(2)}
          </span>
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

      {/* ═══ Performance Metrics ═══ */}
      <div className="stat-card monthly-pnl">
        <div className="stat-card-label">Paper Trade Performance</div>
        <div className="perf-metrics">
          <div className="perf-row">
            <span className="perf-label">Sharpe</span>
            <span className={`perf-value ${(stats.sharpe_ratio || 0) >= 0 ? 'up' : 'down'}`}>
              {stats.sharpe_ratio != null ? stats.sharpe_ratio.toFixed(1) : 'N/A'}
            </span>
          </div>
          <div className="perf-row">
            <span className="perf-label">Win Rate</span>
            <span className="perf-value">{stats.win_rate != null ? stats.win_rate.toFixed(1) : '0.0'}%</span>
          </div>
          <div className="perf-row">
            <span className="perf-label">Profit Factor</span>
            <span className={`perf-value ${(stats.profit_factor || 0) >= 1 ? 'up' : 'down'}`}>
              {stats.profit_factor != null ? (typeof stats.profit_factor === 'number' ? stats.profit_factor.toFixed(2) : stats.profit_factor) : 'N/A'}
            </span>
          </div>
        </div>
      </div>

      {/* ═══ Open Positions ═══ */}
      <div className="stat-card positions">
        {(() => {
          const longN = positionsSummary.total_long_positions || 0
          const shortN = positionsSummary.total_short_positions || 0
          const longPnl = positionsSummary.total_long_pnl || 0
          const shortPnl = positionsSummary.total_short_pnl || 0
          const totalN = longN + shortN
          const netPnl = longPnl + shortPnl
          const longPct = totalN > 0 ? (longN / totalN) * 100 : 50
          return (
            <>
              <div className="pos-head">
                <span className="stat-card-label">Open Positions</span>
                <span className="pos-open-count">{totalN} open</span>
              </div>
              <div className={`pos-net ${netPnl >= 0 ? 'up' : 'down'}`}>
                {netPnl >= 0 ? '+' : ''}${netPnl.toFixed(2)}
                <span className="pos-net-label">net P&L</span>
              </div>
              <div className="pos-split-bar">
                <div className="pos-split-long" style={{ width: `${longPct}%` }} />
                <div className="pos-split-short" style={{ width: `${100 - longPct}%` }} />
              </div>
              <div className="pos-ls-grid">
                <div className="pos-ls long">
                  <span className="pos-ls-tag">LONG {longN}</span>
                  <span className={`pos-ls-pnl ${longPnl >= 0 ? 'up' : 'down'}`}>
                    {longPnl >= 0 ? '+' : ''}${longPnl.toFixed(2)}
                  </span>
                </div>
                <div className="pos-ls short">
                  <span className="pos-ls-tag">SHORT {shortN}</span>
                  <span className={`pos-ls-pnl ${shortPnl >= 0 ? 'up' : 'down'}`}>
                    {shortPnl >= 0 ? '+' : ''}${shortPnl.toFixed(2)}
                  </span>
                </div>
              </div>

              {mt5?.positions?.length > 0 && (
                <div className="pos-live">
                  {mt5.positions.slice(0, 3).map(pos => (
                    <div key={pos.ticket} className="pos-live-row">
                      <span className="pos-live-sym">
                        {pos.symbol.replace('m','')}
                        <span className={pos.type === 0 ? 'up' : 'down'}> {pos.type === 0 ? 'BUY' : 'SELL'}</span>
                      </span>
                      <span className={`pos-live-pnl ${pos.profit >= 0 ? 'up' : 'down'}`}>
                        {pos.profit >= 0 ? '+' : ''}${pos.profit?.toFixed(2)}
                      </span>
                    </div>
                  ))}
                  {mt5.positions.length > 3 && (
                    <div className="pos-live-more">+{mt5.positions.length - 3} more</div>
                  )}
                </div>
              )}
            </>
          )
        })()}
      </div>

      {/* ═══ Forex Agent Stats ═══ */}
      <div className="stat-card dca-top-card">
        <div className="stat-card-label">Agent Status</div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 5 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 8, color: 'var(--text-muted)', marginBottom: 1 }}>🤖 Active</div>
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
          <span>MODE <strong>{summary.paper_mode ? 'PAPER' : 'LIVE'}</strong></span>
          <span>EQUITY <strong>${equity.toFixed(2)}</strong></span>
        </div>
      </div>
    </div>
  )
}
