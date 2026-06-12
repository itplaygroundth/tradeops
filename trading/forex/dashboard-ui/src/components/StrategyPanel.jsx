export default function StrategyPanel({ strategies }) {
  if (!strategies || Object.keys(strategies).length === 0) {
    return (
      <div className="strategy-section">
        <div className="panel-title" style={{ padding: '0 0 8px 0' }}><span>Strategy Performance</span></div>
        <div className="empty-state">Awaiting strategy data...</div>
      </div>
    )
  }

  return (
    <div className="strategy-section">
      <div className="panel-title" style={{ padding: '0 0 8px 0' }}><span>Strategy Performance</span></div>
      {Object.entries(strategies).map(([name, s]) => {
        const spnl = s.avg_pnl_pct || 0
        const pnlClass = spnl >= 0 ? 'pos' : 'neg'
        return (
          <div className="strategy-card" key={name}>
            <div className="strategy-header">
              <span className="strategy-name">{name.replace(/_/g, ' ').toUpperCase()}</span>
              <span className="strategy-count">{s.count} agents</span>
            </div>
            <div className={`strategy-pnl ${pnlClass}`}>
              {spnl >= 0 ? '+' : ''}{spnl.toFixed(2)}%
            </div>
            <div className="strategy-trades">
              {s.trades} trades · {s.win_rate?.toFixed(1) || '0.0'}% WR
            </div>
          </div>
        )
      })}
    </div>
  )
}
