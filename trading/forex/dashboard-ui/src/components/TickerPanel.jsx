export default function TickerPanel({ prices = {} }) {
  const DEFAULT = ['EURUSDm', 'GBPUSDm', 'USDJPYm', 'XAUUSDm', 'AUDUSDm', 'USDCADm', 'USDCHFm', 'NZDUSDm']
  // Use keys from `prices` when available, otherwise fall back to DEFAULT
  const symbols = Object.keys(prices).length ? Object.keys(prices).slice(0, 10) : DEFAULT

  return (
    <div className="ticker">
      {symbols.map((sym) => {
        const p = prices[sym] || {}
        // Prefer MT5-style fields when available
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

        const priceStr = typeof price === 'number'
          ? `$${price.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`
          : '—'

        return (
          <div className="ticker-row" key={sym}>
            <span className="ticker-symbol">{sym}</span>
            <span className="ticker-price">{priceStr}</span>
            <span className={`ticker-change ${changeClass}`}>{changeStr}</span>
          </div>
        )
      })}
    </div>
  )
}
