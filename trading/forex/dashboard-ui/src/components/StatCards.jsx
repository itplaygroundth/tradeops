export default function StatCards({ summary, mt5 }) {
  if (!summary) return null

  const pnlPct = summary.total_pnl_pct || 0
  const pnlDollar = summary.total_pnl || 0
  const equity = summary.total_equity || 0
  const trades = summary.total_trades || 0
  const winners = summary.winners || 0
  const losers = summary.losers || 0
  const initial = summary.total_initial_capital || 100000

  // Paper trade data
  const paperTrade = summary.paper_trade || {}
  const stats = paperTrade.statistics || {}
  const positionsSummary = paperTrade.positions_summary || {}
  const tradeJournal = summary.trade_journal || {}

  // Forex live prices
  const prices = summary.prices || {}
  const fxSymbols = ['EURUSDm', 'GBPUSDm', 'XAUUSDm']
  const fxBooks = fxSymbols.map(sym => ({ sym: sym.replace('m',''), data: prices[sym] || {} }))

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
            FILLED <strong>{stats.total_orders_filled || trades}</strong>
          </span>
        </div>
        <div className="stat-card-footer">
          <span>TRADES <strong>{trades}</strong></span>
          <span>FEES <strong>${stats.total_fees_collected?.toFixed(2) || '0.00'}</strong></span>
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
          <div className="perf-row">
            <span className="perf-label">Edge Ratio</span>
            <span className={`perf-value ${(summary.edge_ratio || 0) >= 1 ? 'up' : 'down'}`}>
              {summary.edge_ratio != null ? summary.edge_ratio.toFixed(3) : 'N/A'}
            </span>
          </div>
          <div className="perf-row">
            <span className="perf-label">Total PnL</span>
            <span className={`perf-value ${(stats.total_pnl || 0) >= 0 ? 'up' : 'down'}`}>
              ${stats.total_pnl?.toFixed(2) || '0.00'}
            </span>
          </div>
        </div>
        <div className="stat-card-footer">
          <span>ORDERS <strong>{stats.total_orders_placed || 0}</strong></span>
          <span>FILLED <strong>{stats.total_orders_filled || 0}</strong></span>
        </div>
      </div>

      {/* ═══ Open Positions + Order Book ═══ */}
      <div className="stat-card positions">
        <div className="stat-card-label">Open Positions</div>
        <div className="open-pos-row">
          <div className="pos-side long">
            <span className="pos-badge long">LONG</span>
            <span className="pos-count">{positionsSummary.total_long_positions || 0}</span>
          </div>
          <div className="pos-bar">
            <div className="pos-bar-fill" style={{width: positionsSummary.total_long_positions > 0 || positionsSummary.total_short_positions > 0 ?
              `${((positionsSummary.total_long_positions||0) / ((positionsSummary.total_long_positions||0)+(positionsSummary.total_short_positions||0))) * 100}%` : '50%'}}></div>
          </div>
          <div className="pos-side short">
            <span className="pos-count">{positionsSummary.total_short_positions || 0}</span>
            <span className="pos-badge short">SHORT</span>
          </div>
        </div>
        <div className="pos-pnl-grid">
          <div className={`pos-pnl-item ${(positionsSummary.total_long_pnl||0) >= 0 ? 'win' : 'loss'}`}>
            <span className="pos-pnl-label">LONG PNL</span>
            <span className="pos-pnl-val">
              {(positionsSummary.total_long_pnl||0) >= 0 ? '+' : ''}${positionsSummary.total_long_pnl?.toFixed(2) || '0.00'}
            </span>
          </div>
          <div className={`pos-pnl-item ${(positionsSummary.total_short_pnl||0) >= 0 ? 'win' : 'loss'}`}>
            <span className="pos-pnl-label">SHORT PNL</span>
            <span className="pos-pnl-val">
              {(positionsSummary.total_short_pnl||0) >= 0 ? '+' : ''}${positionsSummary.total_short_pnl?.toFixed(2) || '0.00'}
            </span>
          </div>
        </div>

        {mt5?.positions?.length > 0 && (
          <div style={{ marginTop: 6, borderTop: '0.5px solid rgba(255,255,255,0.07)', paddingTop: 6 }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginBottom: 4 }}>MT5 Live Positions</div>
            {mt5.positions.slice(0, 3).map(pos => (
              <div key={pos.ticket} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 2 }}>
                <span>{pos.symbol} <span style={{ color: pos.type === 0 ? 'var(--green)' : 'var(--red)' }}>{pos.type === 0 ? 'BUY' : 'SELL'}</span></span>
                <span style={{ color: pos.profit >= 0 ? 'var(--green)' : 'var(--red)', fontFamily: "'JetBrains Mono', monospace" }}>
                  {pos.profit >= 0 ? '+' : ''}${pos.profit?.toFixed(2)}
                </span>
              </div>
            ))}
            {mt5.positions.length > 3 && (
              <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>+{mt5.positions.length - 3} more</div>
            )}
          </div>
        )}

        {/* Forex Live Spread */}
        <div className="order-book-mini">
          <div className="ob-header">
            <span className="ob-card-label">Live Spread</span>
            <span className="ob-label">Bid</span>
            <span className="ob-label">Ask</span>
            <span className="ob-label">Spread</span>
          </div>
          {fxBooks.map(({ sym, data }) => {
            const bid = data.bid
            const ask = data.ask
            const spread = (bid && ask) ? ((ask - bid) / bid * 100) : null
            const dp = sym === 'XAUUSD' ? 2 : 5
            return (
              <div className="ob-row" key={sym}>
                <span className="ob-sym">{sym.replace('USD','')}</span>
                <span className="ob-bid">{bid != null ? bid.toFixed(dp) : '-'}</span>
                <span className="ob-ask">{ask != null ? ask.toFixed(dp) : '-'}</span>
                <span className={`ob-spread ${spread != null && spread < 0.05 ? 'green' : 'red'}`}>
                  {spread != null ? spread.toFixed(3) + '%' : '-'}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* ═══ Forex Agent Stats ═══ */}
      <div className="stat-card dca-top-card">
        <div className="stat-card-label">Agent Status</div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginBottom: 2 }}>🤖 Active</div>
            <strong style={{ fontSize: 20, color: 'var(--gold)', fontFamily: "'JetBrains Mono', monospace" }}>
              {activeAgents}
            </strong>
            <span style={{ fontSize: 9, color: 'var(--text-muted)' }}> / {totalAgents}</span>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginBottom: 2 }}>🎯 Win Rate</div>
            <strong style={{ fontSize: 20, fontFamily: "'JetBrains Mono', monospace", color: winRate >= 50 ? 'var(--green)' : 'var(--red)' }}>
              {winRate.toFixed(1)}%
            </strong>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {[
            { label: 'WIN', val: winners, color: 'var(--green)' },
            { label: 'LOSS', val: losers, color: 'var(--red)' },
            { label: 'TRADES', val: trades, color: 'var(--text-secondary)' },
          ].map(({ label, val, color }) => (
            <div key={label} style={{
              flex: 1, padding: '3px 4px', borderRadius: 4,
              background: 'rgba(255,255,255,0.03)',
              border: '0.5px solid rgba(255,255,255,0.07)',
              textAlign: 'center',
            }}>
              <div style={{ fontSize: 8, color: 'var(--text-muted)', fontWeight: 600 }}>{label}</div>
              <div style={{ fontSize: 14, fontWeight: 800, fontFamily: "'JetBrains Mono', monospace", color }}>
                {val}
              </div>
            </div>
          ))}
        </div>
        <div className="stat-card-footer">
          <span>MODE <strong>{summary.paper_mode ? 'PAPER' : 'LIVE'}</strong></span>
          <span>EQUITY <strong>${equity.toFixed(2)}</strong></span>
        </div>
      </div>
    </div>
  )
}
