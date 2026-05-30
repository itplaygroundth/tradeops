import { useState } from 'react'
import TvChart from './TvChart.jsx'

const SYMBOLS = ['EURUSDm', 'GBPUSDm', 'USDJPYm', 'XAUUSDm', 'USDCADm', 'USDCHFm', 'AUDUSDm', 'NZDUSDm']
const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1']

function symLabel(s) { return s.replace(/m$/i, '') }

export default function TradingPanel() {
  const [symbol, setSymbol] = useState('EURUSDm')
  const [tf, setTf] = useState('M15')

  return (
    <div className="trading-panel">
      <div className="trading-panel-header">
        <div className="trading-symbol-tabs">
          {SYMBOLS.map(s => (
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
