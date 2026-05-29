import { fmtUSD, fmtPrice, fmtPct, clrFor } from '../utils.js'
import Badge from './Badge.jsx'

function TradeRow({ t, i }) {
  const pnl = t.net_pnl || 0
  const sym = (t.symbol || '--').replace('USDT', '').replace('BUSD', '')
  const exitReason = (t.exit_reason || 'signal').replace(/_/g, ' ')
  const exitColor =
    t.exit_reason === 'take_profit' ? '#0ECB81'
    : t.exit_reason === 'stop_loss' ? '#F6465D'
    : '#848E9C'
  const dur = t.duration_seconds
    ? t.duration_seconds >= 3600 ? Math.round(t.duration_seconds / 3600) + 'h'
      : t.duration_seconds >= 60 ? Math.round(t.duration_seconds / 60) + 'm'
      : Math.round(t.duration_seconds) + 's'
    : '--'

  return (
    <div
      className="px-4 py-3.5 border-b border-[rgba(255,255,255,0.07)] active:bg-[#1E2329] transition-colors animate-fade-in"
      style={{ animationDelay: `${i * 0.03}s` }}
    >
      {/* Top row */}
      <div className="flex justify-between items-start mb-2.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-[#EAECEF]">{sym}</span>
          <Badge side={t.side} />
          <span
            className="text-[11px] px-1.5 py-0.5 rounded font-semibold"
            style={{
              color: exitColor,
              background: `${exitColor}20`,
              border: `1px solid ${exitColor}30`,
            }}
          >
            {exitReason}
          </span>
        </div>
        <div className="mono text-[16px] font-bold" style={{ color: clrFor(pnl) }}>
          {fmtUSD(pnl)}
        </div>
      </div>

      {/* Detail grid */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { l: 'ENTRY', v: fmtPrice(t.entry_price) },
          { l: 'EXIT', v: fmtPrice(t.exit_price) },
          { l: 'RETURN', v: fmtPct(t.net_pnl_pct || 0), c: clrFor(pnl) },
          { l: 'DUR', v: dur },
        ].map(({ l, v, c }) => (
          <div key={l}>
            <div className="text-[10px] text-[#5E6673] uppercase tracking-widest mb-1">{l}</div>
            <div className="mono text-[12px] font-medium" style={{ color: c || '#EAECEF' }}>{v}</div>
          </div>
        ))}
      </div>

      <div className="mt-2 text-[10px] text-[#5E6673]">
        {t.agent_name} · {t.entry_time_str || ''}
      </div>
    </div>
  )
}

export default function TradesTab({ data }) {
  const trades = data?.summary?.paper_trade?.recent_trades || []

  if (!trades.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-2">
        <div className="text-4xl opacity-30">📊</div>
        <div className="text-sm font-semibold text-[#848E9C]">No closed trades yet</div>
      </div>
    )
  }

  const wins = trades.filter(t => (t.net_pnl || 0) > 0).length
  const totalPnl = trades.reduce((s, t) => s + (t.net_pnl || 0), 0)

  return (
    <div>
      <div className="flex justify-between items-center px-4 py-2.5 bg-[#1E2329] border-b border-[rgba(255,255,255,0.07)]">
        <span className="text-xs text-[#848E9C]">
          {trades.length} trades · {wins}W / {trades.length - wins}L
        </span>
        <span className="mono text-[13px] font-bold" style={{ color: clrFor(totalPnl) }}>
          {fmtUSD(totalPnl)}
        </span>
      </div>
      {trades.slice(0, 50).map((t, i) => (
        <TradeRow key={t.trade_id || i} t={t} i={i} />
      ))}
    </div>
  )
}
