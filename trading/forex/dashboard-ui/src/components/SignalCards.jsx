export default function SignalCards({ strategies, summary }) {
  const entries = Object.entries(strategies || {})
  const best = entries.length
    ? entries.reduce((a, b) => (a[1].avg_pnl_pct > b[1].avg_pnl_pct ? a : b))
    : null

  return (
    <div className="signal-cards">
      {best && (
        <div className="signal-card best-strat">
          <div className="signal-card-label">🏆 LEADING STRATEGY</div>
          <div className="signal-card-title">{best[0].replace(/_/g, ' ').toUpperCase()}</div>
          <div className="signal-card-sub">
            {best[1].trades} trades · {best[1].win_rate?.toFixed(1) || '0'}% WR · {best[1].count} agents
          </div>
          <div className="signal-card-pnl up">+{best[1].avg_pnl_pct?.toFixed(2) || '0'}%</div>
        </div>
      )}
      {!best && (
        <div className="signal-card wait">
          <div className="signal-card-label">⏳ Awaiting Data</div>
          <div className="signal-card-title">Strategy Performance</div>
          <div className="signal-card-sub">Collecting trade data...</div>
        </div>
      )}
    </div>
  )
}
