
import { useEffect, useState } from 'react'

function fmtTime(ts) {
  try {
    // if ts already in seconds or float
    const t = ts > 1e12 ? ts : ts * 1000
    return new Date(t).toLocaleString('th-TH')
  } catch (e) { return '-' }
}

function toCSV(rows) {
  if (!rows || rows.length === 0) return ''
  const keys = ["timestamp","agent","symbol","action","volume","price","sl","tp","type","status","pnl","ticket"]
  const header = keys.join(',')
  const lines = rows.map(r => keys.map(k => {
    const v = r[k]
    if (v === undefined || v === null) return ''
    return '"' + String(v).replace(/"/g,'""') + '"'
  }).join(','))
  return [header].concat(lines).join('\n')
}

export default function TradeHistory({ orderHistory }) {
  const [rows, setRows] = useState(orderHistory || [])
  const [filter, setFilter] = useState({ q: '', symbol: '', agent: '', status: '' })
  const [detail, setDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [offset, setOffset] = useState((orderHistory || []).length)
  const [loadingMore, setLoadingMore] = useState(false)
  const [stream, setStream] = useState(null)

  useEffect(() => {
    // Fetch initial page from server with filters
    async function loadInitial() {
      try {
        const params = new URLSearchParams({ offset: '0', limit: '100', symbol: filter.symbol || '', agent: filter.agent || '', status: filter.status || '', q: filter.q || '' })
        const res = await fetch(`/api/order_history?${params.toString()}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const j = await res.json()
        setRows(j.items || [])
        setOffset((j.items || []).length)
      } catch (e) {
        setRows(orderHistory || [])
      }
    }
    loadInitial()
    setRows(orderHistory || [])
  }, [orderHistory])

  useEffect(() => {
    // Setup SSE stream
    let es
    try {
      es = new EventSource('/api/order_history/stream')
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          setRows(prev => [data].concat(prev))
          setOffset(prev => prev + 1)
        } catch (e) {
          console.error('sse parse', e)
        }
      }
      setStream(es)
    } catch (e) {
      console.warn('SSE not available', e)
    }
    return () => { if (es) es.close() }
  }, [])

  function filtered() {
    return (rows || []).filter(r => {
      if (filter.symbol && r.symbol !== filter.symbol) return false
      if (filter.agent && r.agent !== filter.agent) return false
      if (filter.status && String(r.status) !== filter.status) return false
      if (filter.q) {
        const q = filter.q.toLowerCase()
        return (r.agent||'').toLowerCase().includes(q) || (r.symbol||'').toLowerCase().includes(q) || (r.action||'').toLowerCase().includes(q)
      }
      return true
    })
  }

  async function exportCSV() {
    const csv = toCSV(filtered())
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `order_history_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function loadMore() {
    setLoadingMore(true)
    try {
      const params = new URLSearchParams({ offset: String(offset), limit: '100', symbol: filter.symbol || '', agent: filter.agent || '', status: filter.status || '', q: filter.q || '' })
      const res = await fetch(`/api/order_history?${params.toString()}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const j = await res.json()
      const items = j.items || []
      setRows(prev => prev.concat(items))
      setOffset(prev => prev + items.length)
    } catch (e) {
      console.error('loadMore error', e)
    } finally {
      setLoadingMore(false)
    }
  }

  // When filters change, reload initial page
  useEffect(() => {
    async function reload() {
      try {
        const params = new URLSearchParams({ offset: '0', limit: '100', symbol: filter.symbol || '', agent: filter.agent || '', status: filter.status || '', q: filter.q || '' })
        const res = await fetch(`/api/order_history?${params.toString()}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const j = await res.json()
        setRows(j.items || [])
        setOffset((j.items || []).length)
      } catch (e) {
        console.error('reload error', e)
      }
    }
    reload()
  }, [filter.symbol, filter.agent, filter.status, filter.q])

  async function showDetail(row) {
    if (!row.ticket) return setDetail({ info: 'No ticket available' })
    setLoadingDetail(true)
    try {
      const res = await fetch(`/api/deal/${row.ticket}`)
      const j = await res.json()
      setDetail(j)
    } catch (e) {
      setDetail({ error: String(e) })
    } finally {
      setLoadingDetail(false)
    }
  }

  const list = filtered()

  return (
    <div className="trade-history panel">
      <div className="panel-title">ประวัติคำสั่ง (Order History)</div>
      <div className="trade-controls">
        <input placeholder="ค้นหา (agent, symbol, action)" value={filter.q} onChange={e=>setFilter({...filter,q:e.target.value})} />
        <input placeholder="Symbol" value={filter.symbol} onChange={e=>setFilter({...filter,symbol:e.target.value})} />
        <input placeholder="Agent" value={filter.agent} onChange={e=>setFilter({...filter,agent:e.target.value})} />
        <select value={filter.status} onChange={e=>setFilter({...filter,status:e.target.value})}>
          <option value="">All</option>
          <option value="open">Open</option>
          <option value="placed">Placed</option>
          <option value="closed">Closed</option>
          <option value="skipped">Skipped</option>
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
              <th>Lot</th>
              <th>Price</th>
              <th>SL</th>
              <th>TP</th>
              <th>Type</th>
              <th>Status</th>
              <th>PnL</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r, i) => (
              <tr key={i} onClick={()=>showDetail(r)} style={{cursor: r.ticket ? 'pointer' : 'default'}}>
                <td>{fmtTime(r.timestamp)}</td>
                <td>{r.agent}</td>
                <td>{r.symbol}</td>
                <td>{r.action}</td>
                <td>{r.volume}</td>
                <td>{r.price ?? '-'}</td>
                <td>{r.sl ?? '-'}</td>
                <td>{r.tp ?? '-'}</td>
                <td>{r.type}</td>
                <td>{r.status ?? (r.type==='closed'? 'closed':'-')}</td>
                <td>{r.pnl !== undefined ? r.pnl : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{textAlign:'center', padding:'8px'}}>
        <button onClick={loadMore} disabled={loadingMore}>{loadingMore ? 'Loading...' : 'Load more'}</button>
      </div>

      {detail && (
        <div className="detail-modal">
          <div className="detail-content">
            <button className="close" onClick={()=>setDetail(null)}>Close</button>
            <pre>{loadingDetail ? 'Loading...' : JSON.stringify(detail, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  )
}
