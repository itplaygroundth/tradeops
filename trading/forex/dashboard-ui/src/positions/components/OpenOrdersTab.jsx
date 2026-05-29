import { fmtUSD, clrFor, symIcon, symBase } from '../utils.js'
import Badge from './Badge.jsx'

function PosRow({ a, idx }) {
  const side = a.signal_action || 'HOLD'
  const isLong = side === 'LONG'
  const isShort = side === 'SHORT'
  const upnl = a.unrealized_pnl || 0
  const sym = a.current_symbol || 'MULTI'
  const sl = a.stop_loss_pct || 0
  const tp = a.take_profit_pct || 0

  const circleColor = isLong
    ? { bg: 'rgba(14,203,129,0.12)', color: '#0ECB81', border: 'rgba(14,203,129,0.2)' }
    : isShort
    ? { bg: 'rgba(246,70,93,0.12)', color: '#F6465D', border: 'rgba(246,70,93,0.2)' }
    : { bg: '#2B3139', color: '#848E9C', border: 'rgba(255,255,255,0.07)' }

  return (
    <div
      className="flex items-center gap-3 px-4 py-3.5 border-b border-[rgba(255,255,255,0.07)] active:bg-[#1E2329] transition-colors animate-fade-in"
      style={{ animationDelay: `${idx * 0.025}s` }}
    >
      {/* Symbol circle */}
      <div
        className="w-10 h-10 rounded-full flex-shrink-0 flex items-center justify-center text-base font-bold border"
        style={{ background: circleColor.bg, color: circleColor.color, borderColor: circleColor.border }}
      >
        {symIcon(sym)}
      </div>

      {/* Name + strategy */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="text-sm font-bold text-[#EAECEF]">{a.name}</span>
          <Badge side={side} />
        </div>
        <div className="text-[11px] text-[#5E6673]">
          {(a.strategy || '--').replace(/_/g, ' ')} · {symBase(sym) || 'MULTI'}
        </div>
      </div>

      {/* PnL + SL/TP */}
      <div className="text-right flex-shrink-0">
        <div className="mono text-[15px] font-bold" style={{ color: clrFor(upnl) }}>
          {fmtUSD(upnl)}
        </div>
        <div className="flex gap-2 justify-end mt-0.5">
          <span className="mono text-[11px] text-[#F6465D]">SL {sl.toFixed(1)}%</span>
          <span className="mono text-[11px] text-[#0ECB81]">TP {tp.toFixed(1)}%</span>
        </div>
      </div>
    </div>
  )
}

export default function OpenOrdersTab({ data }) {
  const agents = (data?.agents || []).filter(a => (a.open_positions || 0) > 0)

  if (!agents.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-2">
        <div className="text-4xl opacity-30">📭</div>
        <div className="text-sm font-semibold text-[#848E9C]">No open positions</div>
        <div className="text-xs text-[#5E6673]">Waiting for signals</div>
      </div>
    )
  }

  const totalUnreal = agents.reduce((s, a) => s + (a.unrealized_pnl || 0), 0)

  return (
    <div>
      <div className="flex justify-between items-center px-4 py-2.5 bg-[#1E2329] border-b border-[rgba(255,255,255,0.07)]">
        <span className="text-xs text-[#848E9C]">{agents.length} positions open</span>
        <span className="mono text-[13px] font-bold" style={{ color: clrFor(totalUnreal) }}>
          Unr. {fmtUSD(totalUnreal)}
        </span>
      </div>
      {agents.map((a, i) => <PosRow key={a.id} a={a} idx={i} />)}
    </div>
  )
}
