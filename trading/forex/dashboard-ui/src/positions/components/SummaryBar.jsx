import { fmtUSD, fmtPct, clrFor } from '../utils.js'

export default function SummaryBar({ s }) {
  const pt = s.paper_trade || {}
  const stats = pt.statistics || {}
  const ps = pt.positions_summary || {}
  const pnl = s.total_pnl || 0
  const pnlPct = s.total_pnl_pct || 0
  const equity = s.total_equity || 0
  const wr = stats.win_rate || 0
  const trades = stats.total_trades_closed || 0

  const wrColor = wr >= 50 ? '#0ECB81' : wr >= 30 ? '#F0B90B' : '#F6465D'

  const statItems = [
    { l: 'Win Rate', v: wr.toFixed(1) + '%', c: wrColor },
    { l: 'Trades', v: trades, c: '#EAECEF' },
    { l: 'Long', v: ps.total_long_positions || 0, c: '#0ECB81' },
    { l: 'Short', v: ps.total_short_positions || 0, c: '#F6465D' },
    { l: 'Realized', v: fmtUSD(s.realized_pnl || 0, 2), c: clrFor(s.realized_pnl || 0) },
    { l: 'Agents', v: s.total_agents || 100, c: '#1E80FF' },
  ]

  return (
    <>
      {/* Equity hero */}
      <div className="px-4 py-3 bg-[#0B0E11]">
        <div className="text-[11px] text-[#848E9C] mb-0.5">Portfolio Equity</div>
        <div className="mono text-[26px] font-bold text-[#EAECEF] tracking-tight">
          ${equity >= 1000
            ? equity.toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            : equity.toFixed(2)}
        </div>
        <div className="mono text-[13px] font-semibold mt-0.5" style={{ color: clrFor(pnl) }}>
          {fmtUSD(pnl)}{' '}
          <span className="text-[12px]" style={{ color: clrFor(pnlPct) }}>
            ({fmtPct(pnlPct)})
          </span>
        </div>
      </div>

      {/* Stats row */}
      <div className="flex overflow-x-auto border-b border-[rgba(255,255,255,0.07)] scrollbar-none">
        {statItems.map(({ l, v, c }) => (
          <div
            key={l}
            className="flex-shrink-0 min-w-[88px] px-3 py-2 border-r border-[rgba(255,255,255,0.07)] last:border-r-0"
          >
            <div className="text-[10px] text-[#5E6673] uppercase tracking-widest mb-1">{l}</div>
            <div className="mono text-[14px] font-semibold" style={{ color: c }}>{v}</div>
          </div>
        ))}
      </div>
    </>
  )
}
