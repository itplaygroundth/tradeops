import { lazy, Suspense, useState, useEffect } from 'react'
import { useLiveState } from './hooks/useLiveState.js'
import Header from './components/Header.jsx'
import StatCards from './components/StatCards.jsx'

// ⚡ Lazy-loaded components
const AgentGrid = lazy(() => import('./components/AgentGrid.jsx'))
const TickerPanel = lazy(() => import('./components/TickerPanel.jsx'))
const TopAgents = lazy(() => import('./components/TopAgents.jsx'))
const TradeHistory = lazy(() => import('./components/TradeHistory.jsx'))
const ChartTabs = lazy(() => import('./components/ChartTabs.jsx'))
const PairManager = lazy(() => import('./components/PairManager.jsx'))

function LazyBox({ children }) {
  return (
    <Suspense fallback={<div className="lazy-placeholder" />}>
      {children}
    </Suspense>
  )
}

export default function App() {
  const { state, error, positions } = useLiveState()
  const [pairsOverride, setPairsOverride] = useState(null)

  if (error && !state) {
    return (
      <div className="app">
        <div className="loading">
          <div className="pulse-dot"></div>
          <span>Connecting to trading engine...</span>
          <small>{error}</small>
        </div>
      </div>
    )
  }

  if (!state) {
    return (
      <div className="app">
        <div className="loading">
          <div className="pulse-dot"></div>
          <span>Loading Ai Trade...</span>
        </div>
      </div>
    )
  }

  const { summary, agents } = state
  const prices = state?.prices || {}
  const orderHistory = state?.order_history || []
  // Pairs come from price feed keys; PairManager edits an override copy
  const pairs = pairsOverride ?? Object.keys(prices)

  return (
    <div className="app">
      <Header summary={summary} />

      <StatCards summary={summary} agents={agents} positions={positions} />

      <div className="main">
        {/* LEFT: Market Watch */}
        <div className="left-panel fox-panel-bg">
          <div className="panel-title"><span>📈 Market Watch</span></div>
          <LazyBox><TickerPanel prices={prices} /></LazyBox>
        </div>

        {/* CENTER: Chart & Terminal */}
        <div className="center-panel">
          <div className="chart-area">
            <LazyBox><ChartTabs positions={positions} symbols={pairs} /></LazyBox>
          </div>
          <BottomTerminal orderHistory={orderHistory} agents={agents} />
        </div>

        {/* RIGHT: Top Agents + Pair Manager */}
        <RightPanel agents={agents} pairs={pairs} onPairsChange={setPairsOverride} />
      </div>

      <Footer />
    </div>
  )
}

function RightPanel({ agents, pairs, onPairsChange }) {
  const [pmOpen, setPmOpen] = useState(false)
  return (
    <div className="right-panel fox-panel-bg">
      <LazyBox><TopAgents agents={agents} /></LazyBox>
      <button className="pair-manager-btn" onClick={() => setPmOpen(true)}>
        ⚙️ Manage Pairs
      </button>
      <Suspense fallback={null}>
        <PairManager
          open={pmOpen}
          onClose={() => setPmOpen(false)}
          pairs={pairs}
          onChange={onPairsChange}
        />
      </Suspense>
    </div>
  )
}

function BottomTerminal({ orderHistory, agents }) {
  const [tab, setTab] = useState('history')
  const tabs = [
    { id: 'history', label: '📜 Trade History', count: orderHistory.length },
    { id: 'agents', label: '🤖 AI Agents', count: agents?.length || 0 },
  ]
  return (
    <div className="bottom-terminal">
      <div className="terminal-tabs">
        {tabs.map(t => (
          <button
            key={t.id}
            className={`terminal-tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {t.count != null && <span className="terminal-tab-count">{t.count}</span>}
          </button>
        ))}
      </div>
      <div className="terminal-panel">
        {tab === 'history' && <LazyBox><TradeHistory orderHistory={orderHistory} /></LazyBox>}
        {tab === 'agents' && <LazyBox><AgentGrid agents={agents} /></LazyBox>}
      </div>
    </div>
  )
}

function Footer() {
  const [timeStr, setTimeStr] = useState('')
  useEffect(() => {
    const upd = () => setTimeStr(new Date().toLocaleString('th-TH', {
      timeZone: 'Asia/Bangkok',
      weekday: 'long',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }))
    upd()
    const id = setInterval(upd, 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="footer">
      <span className="brand">Ai เทรด ..เด้อ · Crypto · SiamSynapse</span>
      <span>{timeStr} ICT</span>
      <span>World-Class WebTrader UI</span>
    </div>
  )
}
