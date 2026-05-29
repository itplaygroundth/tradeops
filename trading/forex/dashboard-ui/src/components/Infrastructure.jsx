import { useState, useEffect } from 'react'

const BRANDS = [
  { name: 'Zeus', logo: '/zeus_logo.jpg' },
  { name: 'thClaws', logo: '/thclaws_logo.jpg' },
  { name: 'Hermes', logo: '/hermes_logo.jpg' },
  { name: 'Ai Trader', logo: '/fox_logo.jpg' },
]

const BRAND_ROW = [...BRANDS, ...BRANDS]

const STRATEGY_DEFS = {
  lstm_momentum: {
    label: 'LSTM Momentum', icon: '📈', color: '#34c759',
    desc: 'ติดตามโมเมนตัมราคาระยะสั้น ใช้ DNA lookback + threshold',
    signal_type: 'Technical',
    how_it_works: 'วัด % change → LONG ถ้าแรงขึ้น > threshold, SHORT ถ้าตก > threshold',
  },
  llm_sentiment: {
    label: 'LLM Sentiment', icon: '🧠', color: '#007aff',
    desc: 'ส่ง market context ไปวิเคราะห์ sentiment ผ่าน bcproxyai LLM',
    signal_type: 'AI / LLM',
    how_it_works: 'LLM วิเคราะห์ราคา+R SI+momentum → JSON action/confidence',
  },
  grid_scalp: {
    label: 'Grid Scalp', icon: '🔲', color: '#ff9500',
    desc: 'Scalp โดยใช้ SMA20 เป็น基准 — deviation ตาม DNA grid_spacing',
    signal_type: 'Technical',
    how_it_works: 'LONG เมื่อราคาต่ำกว่า SMA20 เกิน grid_spacing → SHORT เมื่อสูงกว่า',
  },
  mean_reversion: {
    label: 'Mean Reversion', icon: '↩️', color: '#af52de',
    desc: 'กลับตัวเมื่อ RSI สุดขั้ว — threshold ตาม DNA z-score',
    signal_type: 'Technical',
    how_it_works: 'RSI > 70+(z×10) → SHORT, RSI < 70-(z×10) → LONG',
  },
  forex_macro: {
    label: 'Forex Macro', icon: '🌐', color: '#f0b90b',
    desc: 'Session timing + economic calendar bias',
    signal_type: 'Macro / Session',
    how_it_works: 'London/NY/Asia session → bias | High-impact news window → avoid trading',
  },
}

const TABS = [
  { id: 'arena', label: '🏆 SSTU Arena' },
  { id: 'strategies', label: '🧬 Strategies' },
  { id: 'feed', label: '📋 Trade Feed' },
]

export default function Infrastructure({ summary }) {
  const [activeTab, setActiveTab] = useState('strategies')
  const [arena, setArena] = useState(null)

  // Fetch Persona Signals every 10s (replaces SSTU Arena)
  useEffect(() => {
    const fetchArena = async () => {
      try {
        const r = await fetch('/api/persona-signals')
        if (r.ok) {
          const d = await r.json()
          setArena(d)
        }
      } catch {}
    }
    fetchArena()
    const iv = setInterval(fetchArena, 10000)
    return () => clearInterval(iv)
  }, [])

  const paperTrade = summary?.paper_trade || {}
  const recentTrades = paperTrade.recent_trades || []
  const stats = paperTrade.statistics || {}
  const strategies = summary?.by_strategy || {}
  const arenaSignal = summary?.market_context?.arena || {}
  const discoveredRegistry = summary?.discovered_strategies?.by_strategy || {}
  const sourceComp = summary?.source_comparison || {}

  // Source comparison helpers
  const ruleSource = sourceComp?.by_source?.rule || {}
  const llmSource = sourceComp?.by_source?.llm || {}
  const winner = sourceComp?.winner || null

  // Build dynamic STRATEGY_DEFS — merge base + discovered
  const DYNAMIC_STRATEGIES = { ...STRATEGY_DEFS }
  // Add discovered strategies from registry
  for (const [sid, s] of Object.entries(discoveredRegistry)) {
    if (!DYNAMIC_STRATEGIES[sid]) {
      DYNAMIC_STRATEGIES[sid] = {
        label: s.name,
        icon: s.icon || '✨',
        color: s.color || '#888',
        desc: s.desc || 'Auto-discovered strategy',
        signal_type: s.signal_type || 'Auto',
        how_it_works: s.how_it_works || '',
        is_discovered: true,
        performance_tier: s.performance_tier || 'active',
        total_pnl: s.total_pnl || 0,
        source: s.source || 'rule',
        target_regime: s.target_regime || '',
        why_now: s.why_now || '',
        risk_level: s.risk_level || '',
      }
    }
  }

  // Build activity
  const activity = []
  if (summary?.by_strategy) {
    const strats = Object.entries(summary.by_strategy)
    const total = strats.reduce((s, [_, v]) => s + v.count, 0)
    activity.push(`📊 Paper Trade — ${stats.total_orders_filled || 0} fills | ${stats.total_trades_closed || 0} closed`)
    for (const [name, info] of strats.slice(0, 2)) {
      const pct = info.avg_pnl_pct || 0
      activity.push(`${pct >= 0 ? '🟢' : '🔴'} ${name}: ${info.count} agents (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%)`)
    }
  }
  if (summary?.total_trades) activity.push(`💱 ${summary.total_trades.toLocaleString()} orders`)
  if (stats.total_fees_collected) activity.push(`💰 Fees: $${stats.total_fees_collected.toFixed(2)} | PnL: ${stats.total_pnl >= 0 ? '+' : ''}$${stats.total_pnl?.toFixed(2) || '0'}`)
  activity.push('⚙️ thClaws — MCP Worker (code · web · file · analyze)')
  if (arena?.signals) {
    Object.entries(arena.signals).forEach(([pid, s]) => {
      const dir = s.direction === 'BULLISH' ? '🟢' : s.direction === 'BEARISH' ? '🔴' : '⚪'
      activity.push(`🧠 ${s.name}: ${dir} ${s.direction} (${s.confidence}%) · ${s.reason || ''}`)
    })
  }
  const ACTIVITY_ROW = [...activity, ...activity]

  return (
    <div className="brand-marquee-section">

      {/* ===== Tabs ===== */}
      <div className="infra-tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`infra-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ===== Tab: SSTU Arena ===== */}
      {activeTab === 'arena' && (
        <div className="infra-tab-content">
          {arena && arena.available ? (
            <div className="arena-card">
              <div className="arena-body">
                {/* Aggregate bias bar */}
                <div className="arena-signal-bar">
                  <span className="sg-arena-label">Persona Consensus:</span>
                  <span className={`sg-arena-bias ${arena.bias === 'BULLISH' ? 'bull' : arena.bias === 'BEARISH' ? 'bear' : ''}`}>
                    {arena.bias === 'BULLISH' ? '🟢' : arena.bias === 'BEARISH' ? '🔴' : '⚪'} {arena.bias} ({arena.bias_strength}%)
                  </span>
                </div>
                {Object.entries(arena.signals || {}).map(([pid, s]) => (
                  <div className="arena-row" key={pid}>
                    <div className="arena-row-top">
                      <span className="arena-rank">
                        {s.direction === 'BULLISH' ? '🟢' : s.direction === 'BEARISH' ? '🔴' : '⚪'}
                      </span>
                      <span className="arena-name">{s.name}</span>
                      <span className={`arena-persona-badge persona-${pid}`}>{pid}</span>
                      <span className={`arena-pnl ${s.direction === 'BULLISH' ? 'up' : s.direction === 'BEARISH' ? 'down' : ''}`}>
                        {s.direction} ({s.confidence}%)
                      </span>
                    </div>
                    <div className="arena-row-bottom">
                      <span className="arena-value">{s.reason}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="arena-card">
              <div className="arena-body">
                <div className="empty-state">Loading Persona Signals...</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===== Tab: AI Agent Strategies ===== */}
      {activeTab === 'strategies' && (
        <div className="infra-tab-content">

          {/* Source Comparison Bar */}
          {(ruleSource.count > 0 || llmSource.count > 0) && (
            <div className="source-compare-bar">
              <div className="source-compare-title">⚔️ Rule vs AI (LLM)</div>
              <div className="source-compare-cards">
                <div className={`source-card rule-card ${winner === 'rule' ? 'winning' : ''}`}>
                  <div className="source-card-header">
                    <span className="source-icon">🔧</span>
                    <span className="source-label">Rule-based</span>
                    <span className="source-count">{ruleSource.count} strats</span>
                  </div>
                  <div className="source-card-stats">
                    <div className="source-stat">
                      <span className="source-stat-label">PnL</span>
                      <span className={`source-stat-value ${(ruleSource.total_pnl || 0) >= 0 ? 'up' : 'down'}`}>
                        ${(ruleSource.total_pnl || 0).toFixed(2)}
                      </span>
                    </div>
                    <div className="source-stat">
                      <span className="source-stat-label">Trades</span>
                      <span className="source-stat-value">{ruleSource.total_trades || 0}</span>
                    </div>
                    <div className="source-stat">
                      <span className="source-stat-label">WR</span>
                      <span className="source-stat-value">{(ruleSource.avg_win_rate || 0).toFixed(1)}%</span>
                    </div>
                  </div>
                  {winner === 'rule' && <div className="source-badge-winner">👑 Leading</div>}
                </div>

                <div className="source-divider">VS</div>

                <div className={`source-card llm-card ${winner === 'llm' ? 'winning' : ''}`}>
                  <div className="source-card-header">
                    <span className="source-icon">🤖</span>
                    <span className="source-label">AI (thClaws)</span>
                    <span className="source-count">{llmSource.count} strats</span>
                  </div>
                  <div className="source-card-stats">
                    <div className="source-stat">
                      <span className="source-stat-label">PnL</span>
                      <span className={`source-stat-value ${(llmSource.total_pnl || 0) >= 0 ? 'up' : 'down'}`}>
                        ${(llmSource.total_pnl || 0).toFixed(2)}
                      </span>
                    </div>
                    <div className="source-stat">
                      <span className="source-stat-label">Trades</span>
                      <span className="source-stat-value">{llmSource.total_trades || 0}</span>
                    </div>
                    <div className="source-stat">
                      <span className="source-stat-label">WR</span>
                      <span className="source-stat-value">{(llmSource.avg_win_rate || 0).toFixed(1)}%</span>
                    </div>
                  </div>
                  {winner === 'llm' && <div className="source-badge-winner">👑 Leading</div>}
                </div>
              </div>
              {sourceComp.has_enough_data === false && (
                <div className="source-compare-note">⏳ ต้องการ trades มากกว่านี้เพื่อเปรียบเทียบ...</div>
              )}
            </div>
          )}

          {/* Strategy Cards with Source Badge */}
          <div className="sg-body">
            {Object.entries(DYNAMIC_STRATEGIES).map(([key, def]) => {
              const strat = strategies?.[key]
              const pnl = strat?.avg_pnl_pct
              const isDiscovered = def.is_discovered
              const source = def.source || 'base'
              const sourceBadge = source === 'base' ? { icon: '🏗', label: 'Base', color: '#888' }
                : source === 'rule' ? { icon: '🔧', label: 'Rule', color: '#ff9500' }
                : { icon: '🤖', label: 'AI', color: '#007aff' }
              return (
                <div className={`sg-strategy ${isDiscovered ? 'discovered' : ''}`} key={key}>
                  <div className="sg-strat-header">
                    <span className="sg-strat-icon">{def.icon}</span>
                    <span className="sg-strat-name" style={{ color: def.color }}>{def.label}</span>
                    <span className="sg-strat-type">{def.signal_type}</span>
                    <span className="sg-source-badge" style={{
                      background: `${sourceBadge.color}22`,
                      color: sourceBadge.color,
                      border: `1px solid ${sourceBadge.color}44`,
                      fontSize: '9px',
                      padding: '1px 6px',
                      borderRadius: '8px',
                      fontFamily: 'JetBrains Mono',
                      marginLeft: 'auto',
                    }}>
                      {sourceBadge.icon} {sourceBadge.label}
                    </span>
                    {isDiscovered && <span className="sg-strat-badge-new">NEW</span>}
                  </div>
                  {pnl != null && (
                    <div className="sg-strat-pnl-row">
                      <span className={`sg-strat-pnl ${pnl >= 0 ? 'up' : 'down'}`}>
                        {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}%
                      </span>
                      {strat && <span style={{fontSize:'9px',color:'var(--text-muted)',fontFamily:'JetBrains Mono'}}>({strat.win_rate?.toFixed(1) || '0'}% WR)</span>}
                    </div>
                  )}
                  <div className="sg-strat-desc">{def.desc}</div>
                  <div className="sg-strat-detail">{def.how_it_works}</div>
                  {strat && (
                    <div className="sg-strat-stats">
                      <span>👥 {strat.count} agents</span>
                      <span>💱 {strat.trades} trades</span>
                      <span>🎯 {strat.win_rate?.toFixed(1) || '0'}% WR</span>
                      {def.why_now && <span style={{fontSize:'9px',color:'var(--text-muted)',width:'100%',marginTop:'2px'}}>🎯 {def.why_now}</span>}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ===== Tab: Paper Trade Feed ===== */}
      {activeTab === 'feed' && (
        <div className="infra-tab-content">
          {recentTrades.length > 0 ? (
            <div className="recent-trades-body">
              {recentTrades.slice(0, 10).map((t, i) => {
                const isWin = t.net_pnl > 0
                return (
                  <div className={`trade-card ${isWin ? 'win' : 'loss'}`} key={t.trade_id || i}>
                    <div className="trade-top">
                      <span>{t.side === 'LONG' ? '🟢' : '🔴'}</span>
                      <span className="trade-sym">{t.symbol?.replace('USDT', '')}</span>
                      <span className={`trade-pnl ${isWin ? 'up' : 'down'}`}>
                        {t.net_pnl >= 0 ? '+' : ''}${t.net_pnl?.toFixed(2)}
                      </span>
                    </div>
                    <div className="trade-detail">
                      ${t.entry_price?.toFixed(2)} → ${t.exit_price?.toFixed(2)}
                    </div>
                    <div className="trade-meta">
                      Qty:{t.entry_qty?.toFixed(4)} · {t.duration_seconds?.toFixed(0)}s · Fee:${t.total_fees?.toFixed(2)}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="empty-state">Waiting for trades...</div>
          )}
        </div>
      )}

      {/* ===== Tech Stack ===== */}
      <div className="tech-stack-header">
        <span className="tech-icon">⚡</span>
        <span className="tech-label">AI Tech Stack</span>
        <div className="tech-line" />
        <span className="tech-count">{BRANDS.length}</span>
      </div>
      <div className="brand-marquee-track">
        <div className="brand-marquee-content">
          {BRAND_ROW.map((brand, i) => (
            <span className="tech-item" key={`tech-${i}`}>
              <img src={brand.logo} alt={brand.name} className="tech-brand-logo" />
              <span className="tech-brand-name">{brand.name}</span>
              <span className="tech-sep">|</span>
            </span>
          ))}
        </div>
      </div>

      {/* ===== Agent Activity ===== */}
      {activity.length > 0 && (
        <div className="activity-track">
          <div className="activity-content">
            {ACTIVITY_ROW.map((s, i) => (
              <span className="activity-item" key={`act-${i}`}>
                {s}
                <span className="activity-sep">◆</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
