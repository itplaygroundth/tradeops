import { useState } from 'react'
import TradingPanel from './TradingPanel.jsx'
import OrderBook from './OrderBook.jsx'
import OrderDialog from './OrderDialog.jsx'

export default function ChartTabs({ positions = [], refreshMT5 }) {
  const [tab, setTab] = useState('chart')
  const [selected, setSelected] = useState(null)

  return (
    <div className="chart-tabs">
      <div className="chart-tabs-bar">
        <button
          className={`chart-tab-btn ${tab === 'chart' ? 'active' : ''}`}
          onClick={() => setTab('chart')}
        >
          📈 Asset &amp; Graph
        </button>
        <button
          className={`chart-tab-btn ${tab === 'orders' ? 'active' : ''}`}
          onClick={() => setTab('orders')}
        >
          📋 Order Book
          {positions.length > 0 && (
            <span className="terminal-tab-count">{positions.length}</span>
          )}
        </button>
      </div>

      {tab === 'chart' && (
        <div className="chart-tab-panel">
          <TradingPanel />
        </div>
      )}
      {tab === 'orders' && (
        <div className="chart-tab-panel order-book-panel">
          <OrderBook positions={positions} onSelect={setSelected} />
        </div>
      )}

      {selected && (
        <OrderDialog
          position={selected}
          onClose={() => setSelected(null)}
          onDone={refreshMT5}
        />
      )}
    </div>
  )
}
