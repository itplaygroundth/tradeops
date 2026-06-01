import { lazy, Suspense, useState } from 'react'
import { useLiveState } from './hooks/useLiveState.js'
import Header from './components/Header.jsx'
import StatCards from './components/StatCards.jsx'

// ⚡ Lazy-loaded components
const AgentGrid = lazy(() => import('./components/AgentGrid.jsx'))
const TickerPanel = lazy(() => import('./components/TickerPanel.jsx'))
const ProbabilityCard = lazy(() => import('./components/ProbabilityCard.jsx'))
const Infrastructure = lazy(() => import('./components/Infrastructure.jsx'))
const WalletCard = lazy(() => import('./components/WalletCard.jsx'))
const TradeHistory = lazy(() => import('./components/TradeHistory.jsx'))
const ChartTabs = lazy(() => import('./components/ChartTabs.jsx'))

function LazyBox({ children }) {
  return (
    <Suspense fallback={<div className="lazy-placeholder" />}>
      {children}
    </Suspense>
  )
}

export default function App() {
  const { state, error, mt5 } = useLiveState()

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
  const tickerPrices = summary?.prices || {}
  const orderHistory = state?.order_history || []

  return (
    <div className="app">
      <Header summary={summary} />

      {/* Top Stat Cards — loaded eagerly, always above fold */}
      <StatCards summary={summary} mt5={mt5} />

      <div className="main">
        {/* LEFT: Market Watch & Gauges */}
        <div className="left-panel fox-panel-bg">
          <LazyBox><WalletCard summary={summary} mt5={mt5} /></LazyBox>
          <div className="panel-title"><span>📈 Market Watch</span></div>
          <LazyBox><TickerPanel prices={tickerPrices} /></LazyBox>
          <LazyBox><ProbabilityCard summary={summary} /></LazyBox>
        </div>

        {/* CENTER: Chart & Terminal */}
        <div className="center-panel">
          <div className="chart-area">
            <LazyBox><ChartTabs positions={mt5?.positions ?? []} /></LazyBox>
          </div>
          
          {/* BOTTOM TERMINAL */}
          <BottomTerminal orderHistory={orderHistory} agents={agents} summary={summary} />
        </div>
      </div>

      <Footer />
    </div>
  )
}

function BottomTerminal({ orderHistory, agents, summary }) {
  const [tab, setTab] = useState('history')
  const tabs = [
    { id: 'history', label: '📜 Trade History', count: orderHistory.length },
    { id: 'agents', label: '🤖 AI Agents', count: agents?.length || 0 },
    { id: 'infra', label: '🛰️ Infrastructure' },
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
        {tab === 'infra' && <LazyBox><Infrastructure summary={summary} /></LazyBox>}
      </div>
    </div>
  )
}

function Footer() {
  const now = new Date()
  const timeStr = now.toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    weekday: 'long',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  return (
    <div className="footer">
      <span className="brand">Ai เทรด ..เด้อ · SiamSynapse</span>
      <span>{timeStr} ICT</span>
      <span>World-Class WebTrader UI</span>
    </div>
  )
}