import { useState } from 'react'
import { fmtUSD, clrFor } from '../utils.js'
import Badge from './Badge.jsx'

const FILTERS = [['all', 'All'], ['trading', 'Trading'], ['paused', 'Paused']]

export default function AgentsTab({ data }) {
  const [filter, setFilter] = useState('all')
  const agents = data?.agents || []

  const filtered =
    filter === 'trading' ? agents.filter(a => (a.wins || 0) + (a.losses || 0) > 0)
    : filter === 'paused' ? agents.filter(a => a.is_paused)
    : agents

  return (
    <div>
      {/* Filter tabs */}
      <div className="flex border-b border-[rgba(255,255,255,0.07)] bg-[#1E2329]">
        {FILTERS.map(([k, l]) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            className="flex-1 py-2.5 text-xs font-semibold transition-all"
            style={{
              color: filter === k ? '#F0B90B' : '#5E6673',
              borderBottom: filter === k ? '2px solid #F0B90B' : '2px solid transparent',
              background: 'none',
              fontFamily: 'inherit',
            }}
          >
            {l}
          </button>
        ))}
      </div>

      {filtered.map((a, i) => {
        const sig = a.signal_action || 'HOLD'
        const pnl = a.pnl || 0
        const wr = a.win_rate || 0
        const trades = (a.wins || 0) + (a.losses || 0)
        const wrColor = wr >= 50 ? '#0ECB81' : wr >= 30 ? '#F0B90B' : '#F6465D'

        return (
          <div
            key={a.id}
            className="flex items-center gap-2.5 px-4 py-3 border-b border-[rgba(255,255,255,0.07)] active:bg-[#1E2329] transition-colors animate-fade-in"
            style={{ animationDelay: `${i * 0.015}s` }}
          >
            {/* ID */}
            <div className="w-6 text-center text-[11px] text-[#5E6673] font-semibold flex-shrink-0">
              {a.id}
            </div>

            {/* Name + strategy */}
            <div className="flex-1 min-w-0">
              <div
                className="text-[13px] font-bold mb-0.5"
                style={{ color: a.is_paused ? '#5E6673' : '#EAECEF' }}
              >
                {a.name}
              </div>
              <div className="text-[10px] text-[#5E6673]">
                {(a.strategy || '--').replace(/_/g, ' ')}
              </div>
            </div>

            {/* Signal */}
            <Badge side={sig} />

            {/* Win rate */}
            <div className="w-11 text-right flex-shrink-0">
              <div className="mono text-[12px] font-bold" style={{ color: wrColor }}>
                {wr.toFixed(0)}%
              </div>
              <div className="text-[10px] text-[#5E6673]">{trades}t</div>
            </div>

            {/* PnL */}
            <div className="w-16 text-right flex-shrink-0">
              <div className="mono text-[12px] font-bold" style={{ color: clrFor(pnl) }}>
                {fmtUSD(pnl)}
              </div>
              {(a.open_positions || 0) > 0 && (
                <div className="text-[10px] text-[#F0B90B] text-right">{a.open_positions} open</div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
