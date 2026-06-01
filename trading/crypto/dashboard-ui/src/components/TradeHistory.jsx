import { useState } from 'react'
import { symLabel, fmtPrice, fmtUsdt } from '../lib/crypto.js'

function fmtTime(ts) {
  try {
    const t = ts > 1e12 ? ts : ts * 1000
    return new Date(t).toLocaleString('th-TH')
  } catch { return '-' }
}

function toCSV(rows) {
  if (!rows || rows.length === 0) return ''
  const keys = ['timestamp', 'agent', 'symbol', 'action', 'volume', 'price', 'pnl', 'status']
  const header = keys.join(',')
  const lines = rows.map(r => keys.map(k => {
    const v = r[k]
    if (v === undefined || v === null) return ''
    return '"' + String(v).replace(/"/g, '""') + '"'
  }).join(','))
  return [header].concat(lines).join('\n')
}

export default function TradeHistory({ orderHistory = [] }) {
  const [filter, setFilter] = useState({ q: '', symbol: '', agent: '', status: '' })

  function filtered() {
    return (orderHistory || []).filter(r => {
      if (filter.symbol && r.symbol !== filter.symbol) return false
      if (filter.agent && r.agent !== filter.agent) return false
      if (filter.status && String(r.status) !== filter.status) return false
      if (filter.q) {
        const q = filter.q.toLowerCase()
        return (r.agent || '').toLowerCase().includes(q) ||
          (r.symbol || '').toLowerCase().includes(q) ||
          (r.action || '').toLowerCase().includes(q)
      }
      return true
    })
  }

  function exportCSV() {
    const csv = toCSV(filtered())
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `order_history_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const list = filtered()

  return (
    <div className="trade-history panel">
      <div className="panel-title">ประวัติคำสั่ง (Order History)</div>
      <div className="trade-controls">
        <input placeholder="ค้นหา (agent, symbol, action)" value={filter.q} onChange={e => setFilter({ ...filter, q: e.target.value })} />
        <input placeholder="Symbol" value={filter.symbol} onChange={e => setFilter({ ...filter, symbol: e.target.value })} />
        <input placeholder="Agent" value={filter.agent} onChange={e => setFilter({ ...filter, agent: e.target.value })} />
        <select value={filter.status} onChange={e => setFilter({ ...filter, status: e.target.value })}>
          <option value="">All</option>
          <option value="open">Open</option>
          <option value="closed">Closed</option>
        </select>
        <button onClick={exportCSV}>Export CSV</button>
      </div>
      <div className="history-table">
        <table>
          <thead>
            <tr>
              <th>เวลา</th>
              <th>Agent</th>
              <th>Symbol</th>
              <th>Action</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Status</th>
              <th>PnL</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r, i) => (
              <tr key={i}>
                <td>{fmtTime(r.timestamp)}</td>
                <td>{r.agent}</td>
                <td>{symLabel(r.symbol)}</td>
                <td className={`th-action ${/buy|long/i.test(r.action) ? 'up' : /sell|short/i.test(r.action) ? 'down' : ''}`}>{r.action}</td>
                <td>{r.volume}</td>
                <td>{typeof r.price === 'number' ? fmtPrice(r.price) : (r.price ?? '-')}</td>
                <td>
                  <span className={`th-status th-status-${String(r.status ?? '').toLowerCase()}`}>
                    {r.status ?? '-'}
                  </span>
                </td>
                <td className={r.pnl > 0 ? 'th-pnl up' : r.pnl < 0 ? 'th-pnl down' : 'th-pnl'}>
                  {r.pnl !== undefined && r.pnl !== null ? (r.pnl > 0 ? '+' : '') + fmtUsdt(Number(r.pnl)) : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
