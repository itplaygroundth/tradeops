import { useState } from 'react'
import { useLiveState } from './hooks/useLiveState.js'
import SummaryBar from './components/SummaryBar.jsx'
import ReportBtn from './components/ReportBtn.jsx'
import OpenOrdersTab from './components/OpenOrdersTab.jsx'
import AgentsTab from './components/AgentsTab.jsx'
import TradesTab from './components/TradesTab.jsx'

const TABS = [
  { id: 'orders', label: 'Orders', icon: '📋' },
  { id: 'agents', label: 'Agents', icon: '🤖' },
  { id: 'trades', label: 'History', icon: '📈' },
]

function LiveDot() {
  return (
    <span
      className="inline-block w-[7px] h-[7px] rounded-full bg-[#0ECB81] animate-pulse-dot flex-shrink-0"
      style={{ boxShadow: '0 0 6px #0ECB81' }}
    />
  )
}

export default function PositionsApp() {
  const { data, ts } = useLiveState()
  const [tab, setTab] = useState('orders')
  const s = data?.summary || {}

  return (
    <div className="min-h-screen bg-[#0B0E11]" style={{ paddingBottom: 72 }}>

      {/* Header */}
      <div
        className="bg-[#161A1E] border-b border-[rgba(255,255,255,0.07)] sticky top-0 z-50"
        style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}
      >
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <LiveDot />
            <span className="text-base font-bold text-[#EAECEF] tracking-tight">AI Trading</span>
            <span className="mono text-[11px] text-[#5E6673]">{ts || '--:--:--'}</span>
          </div>
          <ReportBtn />
        </div>
        {data && <SummaryBar s={s} />}
      </div>

      {/* Tab content */}
      <div key={tab}>
        {tab === 'orders' && <OpenOrdersTab data={data} />}
        {tab === 'agents' && <AgentsTab data={data} />}
        {tab === 'trades' && <TradesTab data={data} />}
      </div>

      {/* Bottom tab bar */}
      <div
        className="fixed bottom-0 left-0 right-0 bg-[#161A1E] border-t border-[rgba(255,255,255,0.07)] flex z-50"
        style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
      >
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className="flex-1 flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium transition-colors"
            style={{
              color: tab === t.id ? '#F0B90B' : '#5E6673',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            <span className="text-xl leading-none">{t.icon}</span>
            <span>{t.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
