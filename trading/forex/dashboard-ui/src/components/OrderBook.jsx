function symLabel(s = '') { return s.replace(/m$/i, '') }

function fmt(v, digits = 5) {
  return typeof v === 'number' ? v.toFixed(digits) : '—'
}

function priceDigits(symbol = '') {
  if (/JPY/i.test(symbol)) return 3
  if (/XAU|GOLD/i.test(symbol)) return 3
  return 5
}

function sideOf(p) {
  if (p.type === 0) return 'BUY'
  if (p.type === 1) return 'SELL'
  return String(p.type || '').toUpperCase()
}

function triggerInfo(p) {
  const side = sideOf(p)
  const triggerSide = p.tp_trigger_side || (side === 'BUY' ? 'Bid' : 'Ask')
  const triggerPrice = p.tp_trigger_price ?? (side === 'BUY' ? p.bid : p.ask) ?? p.price_current
  return { side, triggerSide, triggerPrice }
}

export default function OrderBook({ positions = [], onSelect }) {
  if (!positions.length) {
    return (
      <div className="order-book-empty">
        No open positions
      </div>
    )
  }

  return (
    <div className="order-book">
      <table className="order-book-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Lots</th>
            <th>Open</th>
            <th>Bid/Ask</th>
            <th>Trigger</th>
            <th>P&amp;L</th>
            <th>SL</th>
            <th>TP</th>
            <th>To TP</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(p => {
            const digits = priceDigits(p.symbol)
            const { side, triggerSide, triggerPrice } = triggerInfo(p)
            const distance = p.tp_distance
            return (
              <tr key={p.ticket} className="ob-row" onClick={() => onSelect?.(p)}>
                <td className="ob-symbol">{symLabel(p.symbol)}</td>
                <td className={`ob-side ${side === 'BUY' ? 'ob-buy' : 'ob-sell'}`}>
                  {side}
                </td>
                <td className="ob-lots">{p.volume}</td>
                <td className="ob-open">{fmt(p.price_open, digits)}</td>
                <td className="ob-current">
                  <span className="ob-quote">B {fmt(p.bid, digits)}</span>
                  <span className="ob-quote">A {fmt(p.ask, digits)}</span>
                </td>
                <td className="ob-trigger">
                  <span>{triggerSide}</span>
                  <strong>{fmt(triggerPrice, digits)}</strong>
                </td>
                <td className={`ob-pnl ${p.profit >= 0 ? 'ob-profit' : 'ob-loss'}`}>
                  {p.profit >= 0 ? '+' : ''}{fmt(p.profit, 2)}
                </td>
                <td className="ob-sl">{p.sl != null && p.sl !== 0 ? fmt(p.sl, digits) : '—'}</td>
                <td className="ob-tp">{p.tp != null && p.tp !== 0 ? fmt(p.tp, digits) : '—'}</td>
                <td className={`ob-distance ${p.tp_hit ? 'hit' : ''}`}>
                  {p.tp_hit ? 'hit' : distance != null ? fmt(distance, digits) : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
