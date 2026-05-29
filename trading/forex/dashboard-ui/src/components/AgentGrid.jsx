export default function AgentGrid({ agents }) {
  if (!agents || agents.length === 0) {
    return <div className="empty-state">No agents loaded</div>
  }

  return (
    <div className="agent-grid">
      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  )
}

function AgentCard({ agent }) {
  const pnl = agent.pnl_pct || 0
  const pnlClass = pnl >= 0 ? 'pos' : 'neg'
  const cardClass = pnl >= 0 ? 'winning' : 'losing'
  const barPct = Math.min(Math.abs(pnl) * 2, 100)
  const strat = (agent.strategy || '').replace(/_/g, ' ').toUpperCase()
  const blinkDelay = Math.random() * 2.0
  const blinkSpeed = 0.08 + Math.random() * 0.4
  const ledDelay = Math.random() * 2.0
  const ledSpeed = 0.12 + Math.random() * 0.6

  return (
    <div className={`agent-card ${cardClass}`}>
      <div className="agent-header">
        <span className={`led-dot pnl-blink`} style={{ animationDelay: `${ledDelay}s`, animationDuration: `${ledSpeed}s` }}></span>
        <div className="agent-name">{agent.name}</div>
      </div>
      <div className="agent-strategy">{strat}</div>
      <div className={`agent-pnl ${pnlClass} pnl-blink`} style={{ animationDelay: `${blinkDelay}s`, animationDuration: `${blinkSpeed}s` }}>
        {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}%
      </div>
      <div className="agent-equity">${(agent.equity || 0).toFixed(0)}</div>
      <div className={`pnl-bar ${pnlClass}`} style={{ width: `${barPct}%` }}></div>
    </div>
  )
}
