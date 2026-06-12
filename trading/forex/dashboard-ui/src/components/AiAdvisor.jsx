export default function AiAdvisor({ summary }) {
  if (!summary) return null

  const pnl = summary.total_pnl_pct || 0
  const trades = summary.total_trades || 0
  const winners = summary.winners || 0
  const losers = summary.losers || 0
  const winRate = (winners + losers) > 0
    ? ((winners / (winners + losers)) * 100).toFixed(1)
    : '0.0'

  let advice = 'Market is neutral for now. '
  if (pnl > 50) advice = 'Strong upward momentum detected. Consider holding long positions. '
  else if (pnl > 10) advice = 'Market showing positive bias. Maintain current strategy. '
  else if (pnl < -10) advice = 'Market under pressure. Tighten stop losses. '
  else advice = 'Price consolidation detected. Patience recommended. '

  advice += `Win rate at ${winRate}% across ${trades} trades. `

  if (winRate > 50) advice += 'System performing well. Continue current configuration.'
  else advice += 'Consider adjusting entry thresholds for better selectivity.'

  return (
    <div className="ai-advisor">
      <div className="ai-advisor-header">
        <span className="ai-advisor-icon">💡</span>
        <span className="ai-advisor-title">AI Advisor</span>
      </div>
      <div className="ai-advisor-text">{advice}</div>
      <div className="ai-advisor-tags">
        <span className="advice-tag neutral">Neutral</span>
        <span className="advice-tag info">{winRate}% WR</span>
      </div>
    </div>
  )
}
