import { symLabel, fmtPrice } from '../lib/crypto.js'

const DEFAULT = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']

export default function TickerPanel({ prices = {} }) {
  const symbols = Object.keys(prices).length ? Object.keys(prices).slice(0, 12) : DEFAULT

  return (
    <div className="ticker">
      {symbols.map((sym) => {
        const p = prices[sym] || {}
        const change = p.change_pct
        let price = p.mid ?? p.price
        if (price === undefined && p.bid !== undefined && p.ask !== undefined) {
          price = (p.bid + p.ask) / 2
        }

        let changeStr = '—'
        let changeClass = ''
        if (change !== undefined && change !== null) {
          changeStr = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`
          changeClass = change > 0 ? 'pos' : (change < 0 ? 'neg' : '')
        }

        const priceStr = typeof price === 'number' ? fmtPrice(price) : '—'

        return (
          <div className="ticker-row" key={sym}>
            <span className="ticker-symbol">{symLabel(sym)}</span>
            <span className="ticker-price">{priceStr}</span>
            <span className={`ticker-change ${changeClass}`}>{changeStr}</span>
          </div>
        )
      })}
    </div>
  )
}
