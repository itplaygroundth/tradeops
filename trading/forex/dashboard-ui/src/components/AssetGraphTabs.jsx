import { useEffect, useMemo, useState } from 'react'
import TvChart from './TvChart.jsx'

function symbolLabel(sym) {
  return sym.replace(/m$/i, '')
}

function formatPrice(value) {
  if (typeof value !== 'number') return '—'
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 5 })
}

function formatChange(value) {
  if (typeof value !== 'number') return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

export default function AssetGraphTabs({ prices = {}, agents = [], summary = {} }) {
  const symbols = useMemo(() => {
    const keys = Object.keys(prices)
    if (keys.length) return keys.slice(0, 8)
    const uniqueAgents = Array.from(new Set((agents || []).map(a => a.symbol).filter(Boolean)))
    if (uniqueAgents.length) return uniqueAgents.slice(0, 8)
    return ['EURUSDm', 'GBPUSDm', 'XAUUSDm', 'AUDUSDm', 'USDCADm', 'USDCHFm', 'NZDUSDm']
  }, [prices, agents])

  const [activeSymbol, setActiveSymbol] = useState(symbols[0] || '')

  useEffect(() => {
    if (symbols.length && !symbols.includes(activeSymbol)) setActiveSymbol(symbols[0])
  }, [symbols, activeSymbol])

  const activeData = useMemo(() => {
    if (!activeSymbol) return {}
    const data = prices[activeSymbol] || {}
    const currentPrice = data.mid ?? data.price ?? (data.bid != null && data.ask != null ? (data.bid + data.ask) / 2 : undefined)
    return { currentPrice, change: data.change_pct ?? data.change, bid: data.bid, ask: data.ask }
  }, [activeSymbol, prices])

  return (
    <div className="asset-graph-tabs">
      <div className="asset-tabs">
        {symbols.map(sym => (
          <button
            key={sym}
            type="button"
            className={`asset-tab ${activeSymbol === sym ? 'active' : ''}`}
            onClick={() => setActiveSymbol(sym)}
          >
            {symbolLabel(sym)}
          </button>
        ))}
      </div>
      <div className="asset-graph-card">
        <div className="chart-header">
          <span className="chart-title">💹 {symbolLabel(activeSymbol)}</span>
          <span className={`chart-change ${(activeData.change ?? 0) >= 0 ? 'up' : 'down'}`}>
            {formatChange(activeData.change)}
          </span>
        </div>
        <TvChart symbol={activeSymbol} timeframe="M15" height={160} showVolume={false} showCrosshair />
        <div className="asset-graph-meta">
          <div>
            <div className="asset-meta-label">Price</div>
            <div className="asset-meta-value">{formatPrice(activeData.currentPrice)}</div>
          </div>
          <div>
            <div className="asset-meta-label">Change</div>
            <div className={`asset-meta-value ${(activeData.change ?? 0) >= 0 ? 'up' : 'down'}`}>
              {formatChange(activeData.change)}
            </div>
          </div>
          <div>
            <div className="asset-meta-label">Spread</div>
            <div className="asset-meta-value">
              {activeData.bid != null && activeData.ask != null
                ? (activeData.ask - activeData.bid).toFixed(5)
                : '—'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
