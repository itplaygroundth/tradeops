import { useState, useEffect } from 'react'
import TvChart from './TvChart.jsx'
import { symLabel } from '../lib/crypto.js'

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']

export default function TradingPanel({ symbols = [] }) {
  const list = symbols.length ? symbols : ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
  const [symbol, setSymbol] = useState(list[0])
  const [tf, setTf] = useState('15m')

  // If the active symbol is removed from the list, fall back to the first
  useEffect(() => {
    if (!list.includes(symbol)) setSymbol(list[0])
  }, [list, symbol])

  return (
    <div className="trading-panel">
      <div className="trading-panel-header">
        <div className="trading-symbol-tabs">
          {list.map(s => (
            <button
              key={s}
              className={`trading-sym-tab ${symbol === s ? 'active' : ''}`}
              onClick={() => setSymbol(s)}
            >
              {symLabel(s)}
            </button>
          ))}
        </div>
        <div className="trading-tf-bar">
          {TIMEFRAMES.map(t => (
            <button
              key={t}
              className={`trading-tf-btn ${tf === t ? 'active' : ''}`}
              onClick={() => setTf(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <TvChart symbol={symbol} timeframe={tf} showVolume showCrosshair />
    </div>
  )
}
