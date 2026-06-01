function symLabel(s) { return s.replace(/m$/i, '') }

function fmt(v, digits = 5) {
  return typeof v === 'number' ? v.toFixed(digits) : '—'
}

export default function OrderBook({ positions = [] }) {
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
            <th>Current</th>
            <th>P&amp;L</th>
            <th>SL</th>
            <th>TP</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(p => (
            <tr key={p.ticket}>
              <td className="ob-symbol">{symLabel(p.symbol)}</td>
              <td className={`ob-side ${p.type === 'BUY' ? 'ob-buy' : 'ob-sell'}`}>
                {p.type}
              </td>
              <td className="ob-lots">{p.volume}</td>
              <td className="ob-open">{fmt(p.price_open)}</td>
              <td className="ob-current">{fmt(p.price_current)}</td>
              <td className={`ob-pnl ${p.profit >= 0 ? 'ob-profit' : 'ob-loss'}`}>
                {p.profit >= 0 ? '+' : ''}{fmt(p.profit, 2)}
              </td>
              <td className="ob-sl">{p.sl != null && p.sl !== 0 ? fmt(p.sl) : '—'}</td>
              <td className="ob-tp">{p.tp != null && p.tp !== 0 ? fmt(p.tp) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
