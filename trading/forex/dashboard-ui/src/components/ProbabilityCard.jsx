export default function ProbabilityCard({ summary }) {
  if (!summary) return null

  const agents = summary.top5 || []
  if (!agents.length) return null

  // Pick the top agent's probabilities if available
  const topAgent = agents[0]
  const probs = topAgent.probabilities || null

  return (
    <div className="prob-card">
      <div className="prob-header">
        <span className="prob-title">📊 Probability-Weighted Signals</span>
        <span className="prob-subtitle">Agent consensus distribution</span>
      </div>
      <div className="prob-body">
        {probs ? (
          <div className="prob-bars">
            <div className="prob-bar-row">
              <span className="prob-label long-label">LONG</span>
              <div className="prob-bar-track">
                <div className="prob-bar-fill long" style={{ width: `${probs.LONG * 100}%` }}></div>
              </div>
              <span className="prob-pct">{(probs.LONG * 100).toFixed(1)}%</span>
            </div>
            <div className="prob-bar-row">
              <span className="prob-label hold-label">HOLD</span>
              <div className="prob-bar-track">
                <div className="prob-bar-fill hold" style={{ width: `${probs.HOLD * 100}%` }}></div>
              </div>
              <span className="prob-pct">{(probs.HOLD * 100).toFixed(1)}%</span>
            </div>
            <div className="prob-bar-row">
              <span className="prob-label short-label">SHORT</span>
              <div className="prob-bar-track">
                <div className="prob-bar-fill short" style={{ width: `${probs.SHORT * 100}%` }}></div>
              </div>
              <span className="prob-pct">{(probs.SHORT * 100).toFixed(1)}%</span>
            </div>
          </div>
        ) : (
          <div className="prob-empty">Waiting for agent signals...</div>
        )}
        <div className="prob-info">
          <span className="prob-source">Top agent: {topAgent.name}</span>
          <span className="prob-action">{topAgent.signal_action || topAgent.action || '—'}</span>
        </div>
      </div>
    </div>
  )
}
