export default function DcaRebalanceCard({ summary }) {
  const dca = summary?.dca || {}
  const rebalance = summary?.rebalance || {}
  const pnlBySource = summary?.paper_trade?.pnl_by_source || {}
  const tradePnl = pnlBySource['trade'] || { trades: 0, net_pnl: 0, wins: 0, losses: 0, win_rate: 0 }
  const dcaPnl = pnlBySource['dca'] || { trades: 0, net_pnl: 0, wins: 0, losses: 0, win_rate: 0 }
  const rbPnl = pnlBySource['rebalance'] || { trades: 0, net_pnl: 0, wins: 0, losses: 0, win_rate: 0 }
  const regime = dca?.current_regime || 'SIDEWAYS'

  const regimeIcons = { BEAR: '🐻', BULL: '🐂', HIGH_VOL: '🌪️', SIDEWAYS: '➖' }
  const regimeColors = { BEAR: 'var(--red)', BULL: 'var(--green)', HIGH_VOL: 'var(--gold)', SIDEWAYS: 'var(--text-muted)' }
  const rc = regimeColors[regime] || regimeColors.SIDEWAYS

  return (
    <div className="glass-card dca-card" style={{ padding: 10, animation: 'card-entrance 0.5s ease-out both' }}>
      {/* Header */}
      <div className="gauge-label" style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
        <span style={{ fontSize: 13 }}>📊</span>
        <span style={{ fontWeight: 700, color: 'var(--text-secondary)', letterSpacing: 0.4 }}>DCA + Rebalance</span>
        <span
          style={{
            marginLeft: 'auto', fontSize: 9, fontWeight: 700, padding: '1px 7px',
            borderRadius: 8, color: rc, background: `${rc.replace(')', ',0.1)').replace('var(', '') || 'rgba(255,255,255,0.06)'}`,
            border: `0.5px solid ${rc}`,
          }}
        >{regimeIcons[regime] || '➖'} {regime}</span>
      </div>

      {/* PnL Summary Row */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
        {[
          { label: 'Trade', pnl: tradePnl.net_pnl, icon: '🤖' },
          { label: 'DCA', pnl: dcaPnl.net_pnl, icon: '📉' },
          { label: 'Rebalance', pnl: rbPnl.net_pnl, icon: '⚖️' },
        ].map(({ label, pnl, icon }) => (
          <div key={label} style={{
            flex: 1, padding: '4px 6px', borderRadius: 6,
            background: pnl >= 0 ? 'rgba(52,199,89,0.06)' : 'rgba(255,69,58,0.06)',
            border: `0.5px solid ${pnl >= 0 ? 'rgba(52,199,89,0.15)' : 'rgba(255,69,58,0.15)'}`,
          }}>
            <div style={{ fontSize: 8, color: 'var(--text-muted)', fontWeight: 600, marginBottom: 1 }}>{icon} {label}</div>
            <div style={{
              fontSize: 13, fontWeight: 800, fontFamily: "'JetBrains Mono', monospace",
              color: pnl >= 0 ? 'var(--green)' : 'var(--red)',
              textShadow: pnl >= 0 ? '0 0 6px rgba(52,199,89,0.1)' : '0 0 6px rgba(255,69,58,0.08)',
            }}>
              {pnl >= 0 ? '+' : ''}${(pnl || 0).toFixed(2)}
            </div>
          </div>
        ))}
      </div>

      {/* DCA Section */}
      <div className="dca-block">
        <div className="dca-block-title">🔄 DCA Engine</div>
        <div className="dca-row"><span>Status</span><span className="dca-tag on">ACTIVE</span></div>
        <div className="dca-row"><span>Market</span><strong style={{ color: rc }}>{regime}</strong></div>
        <div className="dca-row"><span>Active Plans</span><strong>{dca?.active_plans_count || 0}</strong></div>
        <div className="dca-row"><span>Filled</span><strong>{dca?.total_filled || 0}/{dca?.total_created || 0}</strong></div>
        {dca?.active_plans?.length > 0 && (
          <div className="dca-plans">
            {dca.active_plans.slice(0, 3).map((plan, i) => (
              <div key={i} className="dca-plan-item">
                <span style={{ fontWeight: 700, fontSize: 10 }}>{plan.symbol}</span>
                <div className="dca-plan-bar"><div className="dca-plan-fill" style={{ width: `${plan.pct_filled}%` }} /></div>
                <span style={{ fontSize: 8, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}>
                  {plan.installments_filled}/{plan.installments_total}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Rebalance Section */}
      <div className="dca-block" style={{ marginTop: 6 }}>
        <div className="dca-block-title">⚖️ Rebalance</div>
        <div className="dca-row"><span>Target</span><strong style={{ color: 'var(--gold)' }}>{rebalance?.target_crypto_pct?.toFixed(0) || 40}% Crypto</strong></div>
        <div className="dca-row"><span>Cycles</span><strong>{rebalance?.total_rebalances || 0}</strong></div>
        <div className="dca-row"><span>Volume</span><strong style={{ fontFamily: "'JetBrains Mono', monospace" }}>${(rebalance?.total_value_adjusted || 0).toFixed(0)}</strong></div>
        {rebalance?.last_actions?.length > 0 && (
          <div style={{ marginTop: 4 }}>
            {rebalance.last_actions.slice(0, 2).map((a, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 9, fontFamily: "'JetBrains Mono', monospace", padding: '2px 4px', borderRadius: 4, background: a.action === 'BUY' ? 'rgba(52,199,89,0.06)' : 'rgba(255,69,58,0.06)', marginTop: 2 }}>
                <span style={{ fontSize: 10 }}>{a.action === 'BUY' ? '🟢' : '🔴'}</span>
                <span style={{ fontWeight: 700 }}>{a.symbol}</span>
                <span style={{ color: a.action === 'BUY' ? 'var(--green)' : 'var(--red)', marginLeft: 'auto' }}>
                  {a.action === 'BUY' ? '+' : '-'}${(a.target_value_usdt || 0).toFixed(0)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}