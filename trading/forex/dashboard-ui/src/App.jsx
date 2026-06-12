import { lazy, Suspense } from 'react'
import { useLiveState } from './hooks/useLiveState.js'
import Header from './components/Header.jsx'
import StatCards from './components/StatCards.jsx'

// ⚡ Lazy-loaded components — split into separate chunks, loaded on demand
const SentimentGauges = lazy(() => import('./components/SentimentGauges.jsx'))
const SignalCards = lazy(() => import('./components/SignalCards.jsx'))
const AgentGrid = lazy(() => import('./components/AgentGrid.jsx'))
const TickerPanel = lazy(() => import('./components/TickerPanel.jsx'))
const StrategyPanel = lazy(() => import('./components/StrategyPanel.jsx'))
const TopAgents = lazy(() => import('./components/TopAgents.jsx'))
const AiAdvisor = lazy(() => import('./components/AiAdvisor.jsx'))
const ProbabilityCard = lazy(() => import('./components/ProbabilityCard.jsx'))
const Infrastructure = lazy(() => import('./components/Infrastructure.jsx'))
const WalletCard = lazy(() => import('./components/WalletCard.jsx'))
const EquityCurveChart = lazy(() => import('./components/EquityCurveChart.jsx'))
const DailyPnLChart = lazy(() => import('./components/DailyPnLChart.jsx'))
const AssetGraphTabs = lazy(() => import('./components/AssetGraphTabs.jsx'))
const TradeHistory = lazy(() => import('./components/TradeHistory.jsx'))
const TradingPanel = lazy(() => import('./components/TradingPanel.jsx'))

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
  const strategies = summary?.by_strategy || {}
  const topAgents = summary?.top5 || []
  const tradeJournal = summary?.trade_journal || {}
  const orderHistory = state?.order_history || []

  return (
    <div className="app">
      <Header summary={summary} />

      {/* Top Stat Cards — loaded eagerly, always above fold */}
      <StatCards summary={summary} mt5={mt5} />

      {/* Middle: everything below the fold is lazy-loaded */}
      <div className="main">
        <div className="middle-left fox-panel-bg">
          <LazyBox><SentimentGauges /></LazyBox>
          <LazyBox><ProbabilityCard summary={summary} /></LazyBox>
          <LazyBox><WalletCard summary={summary} mt5={mt5} /></LazyBox>
          <LazyBox><SignalCards strategies={strategies} summary={summary} /></LazyBox>
        </div>

        <div className="agents-panel">
          <LazyBox><TradingPanel /></LazyBox>
          <div className="panel-title">
            <span>🤖 AI Trading Agents</span>
            <span>{(agents || []).length} / {summary?.total_agents || 100}</span>
          </div>
          <LazyBox><AgentGrid agents={agents} /></LazyBox>
          <LazyBox><Infrastructure summary={summary} /></LazyBox>
        </div>

        <div className="details-panel">
          <LazyBox><TickerPanel prices={tickerPrices} /></LazyBox>
          <LazyBox><StrategyPanel strategies={strategies} /></LazyBox>
          <LazyBox><AssetGraphTabs prices={tickerPrices} agents={agents} summary={summary} /></LazyBox>
          <div className="chart-section">
            <LazyBox><EquityCurveChart data={tradeJournal.equity_curve} /></LazyBox>
            <LazyBox><DailyPnLChart dailyPnl={tradeJournal.daily_pnl} /></LazyBox>
          </div>
          <LazyBox><TopAgents agents={topAgents} /></LazyBox>
          <LazyBox><AiAdvisor summary={summary} /></LazyBox>
          <LazyBox><TradeHistory orderHistory={orderHistory} /></LazyBox>
        </div>
      </div>

      <Footer />
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
      <span>25 Agents · Forex · LLM + Evolution</span>
    </div>
  )
}
