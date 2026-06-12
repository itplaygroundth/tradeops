import { symLabel } from '../lib/crypto.js'

export default function TopAgents({ agents }) {
  const top = [...(agents || [])]
    .sort((a, b) => (b.pnl_pct || 0) - (a.pnl_pct || 0))
    .slice(0, 5)

  return (
    <div className="top-agents">
      <div className="panel-title" style={{ padding: '0 0 6px 0' }}><span>🏆 Top Agents</span></div>
      {top.length === 0 ? (
        <div className="empty-state">Awaiting data...</div>
      ) : (
        top.map((a, i) => {
          const apnl = a.pnl_pct || 0
          const pnlClass = apnl >= 0 ? 'pos' : 'neg'
          return (
            <div className="top-agent-row" key={a.id}>
              <span className="top-agent-rank">#{i + 1}</span>
              <span className="top-agent-name">{a.name}</span>
              <span className="top-agent-strategy">{symLabel(a.symbol)}</span>
              <span className={`top-agent-pnl ${pnlClass}`}>
                {apnl >= 0 ? '+' : ''}{apnl.toFixed(2)}%
              </span>
            </div>
          )
        })
      )}
    </div>
  )
}
