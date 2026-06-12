export default function StrategyLab({ summary }) {
  if (!summary) return null

  const kbd = summary.knowledge || {}
  const regimeData = summary.regime || {}
  const rules = summary.rules || {}
  const discovered = summary.discovered_strategies || {}
  const byStrategy = summary.by_strategy || {}
  const top5 = summary.top5 || []
  const bottom5 = summary.bottom5 || []

  const regime = regimeData.current_regime || 'SCANNING'
  const regimeStability = regimeData.stability_ticks || 0
  const recStrats = regimeData.recommended_strategies || []
  const activePitfalls = kbd.active_pitfalls || {}
  const pitfallCount = Object.keys(activePitfalls).length
  const rulesTotal = rules.total_blocks || 0

  // Sort strategies by fitness
  const strategySorted = Object.entries(byStrategy)
    .map(([name, data]) => ({ name, ...data }))
    .sort((a, b) => (b.avg_pnl_pct || 0) - (a.avg_pnl_pct || 0))

  const regimeColors = {
    TRENDING: '#5e5ce6',
    SIDEWAYS: '#ff9f0a',
    HIGH_VOL: '#ff453a',
    BEARISH: '#ff453a',
    BULLISH: '#30d158',
    MIXED: '#8e8e93',
    SCANNING: '#8e8e93',
  }
  const regimeColor = regimeColors[regime] || '#8e8e93'

  return (
    <div className="strategy-lab">
      {/* ═══ Header ═══ */}
      <div className="sl-header">
        <span className="sl-title">🧬 Strategy Lab</span>
        <span className="sl-subtitle">Discovery Engine — SiamSynapse</span>
      </div>

      <div className="sl-grid">

        {/* ═══ Regime Card ═══ */}
        <div className="sl-card regime-card" style={{ borderColor: regimeColor }}>
          <div className="sl-card-header">
            <span className="sl-badge" style={{ background: regimeColor }}>{regime}</span>
            <span className="sl-meta">stability: {regimeStability} ticks</span>
          </div>
          <div className="sl-card-body">
            <div className="sl-stat-row">
              <span className="sl-stat-label">Recommended Strategies</span>
            </div>
            <div className="sl-rec-strats">
              {recStrats.map((s, i) => (
                <span key={i} className="sl-badge-method">{s.replace(/_/g, ' ')}</span>
              ))}
            </div>
            <div className="sl-stat-row">
              <span className="sl-stat-label">Risk Range</span>
              <span className="sl-stat-val">{regimeData.recommended_risk || '0.2–0.5'}</span>
            </div>
            <div className="sl-stat-row">
              <span className="sl-stat-label">Description</span>
              <span className="sl-stat-val muted">{regimeData.description || 'Analyzing...'}</span>
            </div>
          </div>
        </div>

        {/* ═══ Strategy Leaderboard ═══ */}
        <div className="sl-card leaderboard-card">
          <div className="sl-card-header">
            <span className="sl-card-title">🏆 Strategy Leaderboard</span>
          </div>
          <div className="sl-card-body">
            {strategySorted.length === 0 ? (
              <div className="sl-empty">No strategy data yet</div>
            ) : (
              strategySorted.slice(0, 5).map((s, i) => (
                <div key={s.name} className="sl-leader-row">
                  <span className="sl-rank">#{i + 1}</span>
                  <div className="sl-leader-info">
                    <span className="sl-leader-name">{s.name.replace(/_/g, ' ').toUpperCase()}</span>
                    <span className="sl-leader-wr">WR: {(s.win_rate || 0).toFixed(1)}%</span>
                  </div>
                  <div className="sl-leader-stats">
                    <span className={`sl-leader-pnl ${(s.avg_pnl_pct || 0) >= 0 ? 'pos' : 'neg'}`}>
                      {s.avg_pnl_pct >= 0 ? '+' : ''}{s.avg_pnl_pct?.toFixed(2)}%
                    </span>
                    <span className="sl-leader-trades">{s.trades || 0} trades</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ═══ System Health ═══ */}
        <div className="sl-card health-card">
          <div className="sl-card-header">
            <span className="sl-card-title">🔬 System Status</span>
          </div>
          <div className="sl-card-body">
            {pitfallCount > 0 && (
              <div className="sl-alert danger">
                <span className="sl-alert-icon">⚠️</span>
                <span className="sl-alert-text">
                  {pitfallCount} active pitfall{ pitfallCount > 1 ? 's' : ''}
                </span>
              </div>
            )}
            {rulesTotal > 0 && (
              <div className="sl-alert warn">
                <span className="sl-alert-icon">🛑</span>
                <span className="sl-alert-text">
                  {rulesTotal} trades blocked by Hard Rules
                </span>
              </div>
            )}
            {!pitfallCount && !rulesTotal && (
              <div className="sl-alert ok">
                <span className="sl-alert-icon">✅</span>
                <span className="sl-alert-text">All systems nominal</span>
              </div>
            )}
            <div className="sl-health-detail">
              <div className="sl-stat-row">
                <span className="sl-stat-label">Discovered Strategies</span>
                <span className="sl-stat-val">{discovered.count || 0}</span>
              </div>
              <div className="sl-stat-row">
                <span className="sl-stat-label">Top Agent</span>
                <span className="sl-stat-val">{top5[0]?.name || 'N/A'} {(top5[0]?.pnl_pct || 0) >= 0 ? '+' : ''}{(top5[0]?.pnl_pct || 0).toFixed(2)}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* ═══ Bottom Performers (for evolution review) ═══ */}
        {bottom5.length > 0 && (
          <div className="sl-card bottom-card">
            <div className="sl-card-header">
              <span className="sl-card-title">📉 Evolution Candidates</span>
            </div>
            <div className="sl-card-body">
              {bottom5.slice(0, 5).map((a, i) => (
                <div key={a.id || i} className="sl-bottom-row">
                  <span className="sl-bottom-name">{a.name}</span>
                  <span className={`sl-bottom-pnl ${(a.pnl_pct || 0) >= 0 ? 'pos' : 'neg'}`}>
                    {(a.pnl_pct || 0) >= 0 ? '+' : ''}{(a.pnl_pct || 0).toFixed(2)}%
                  </span>
                  <span className="sl-bottom-trades">{a.trades_count || 0} trades</span>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
