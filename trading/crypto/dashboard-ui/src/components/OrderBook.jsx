import { symLabel, fmtPrice, fmtUsdt } from '../lib/crypto.js'

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
            <th>Qty</th>
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
              <td className="ob-open">{fmtPrice(p.price_open)}</td>
              <td className="ob-current">{fmtPrice(p.price_current)}</td>
              <td className={`ob-pnl ${p.profit >= 0 ? 'ob-profit' : 'ob-loss'}`}>
                {p.profit >= 0 ? '+' : ''}{fmtUsdt(p.profit)}
              </td>
              <td className="ob-sl">{p.sl != null && p.sl !== 0 ? fmtPrice(p.sl) : '—'}</td>
              <td className="ob-tp">{p.tp != null && p.tp !== 0 ? fmtPrice(p.tp) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
