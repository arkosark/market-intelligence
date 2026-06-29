import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MacroBar from './components/MacroBar'
import MarketPulse from './components/MarketPulse'
import Screener from './components/Screener'
import DeepDive from './components/DeepDive'
import Earnings from './components/Earnings'
import Pipeline from './components/Pipeline'
import IntelligenceFeed from './components/IntelligenceFeed'
import ArticleIdeas from './components/ArticleIdeas'
import ChatPanel from './components/ChatPanel'
import './index.css'

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 300000 } } })

const TABS = ['🌡️ Market Pulse', '🔍 Screener', '📊 Deep Dive', '📅 Earnings', '⚡ Pipeline', '🔭 Intel Feed', '💡 Article Ideas'] as const
type Tab = typeof TABS[number]

export default function App() {
  const [tab, setTab] = useState<Tab>('🌡️ Market Pulse')
  const [ddTicker, setDdTicker] = useState('NVDA')

  const snapshot = `Dashboard open on: ${tab}. Current deep dive ticker: ${ddTicker}.`

  return (
    <QueryClientProvider client={qc}>
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2 bg-[#0f1117] border-b border-[#1e2130] flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-base font-bold tracking-tight">📈 Market Intelligence</span>
            <span className="text-[10px] text-[#374151]">Yahoo Finance · 15-min delay</span>
          </div>
          <div className="text-[10px] text-[#374151]">{new Date().toLocaleString()}</div>
        </div>

        {/* Macro bar */}
        <div className="flex-shrink-0">
          <MacroBar/>
        </div>

        {/* Body */}
        <div className="flex flex-1 min-h-0">
          {/* Left column */}
          <div className="flex flex-col flex-1 min-w-0">
            {/* Tabs */}
            <div className="flex border-b border-[#1e2130] bg-[#0a0a0f] px-4 flex-shrink-0 overflow-x-auto">
              {TABS.map(t => (
                <button key={t} onClick={() => setTab(t)}
                  className={`px-4 py-3 text-sm font-semibold transition-colors tracking-wide whitespace-nowrap ${tab === t ? 'tab-active' : 'tab-inactive'}`}>
                  {t}
                </button>
              ))}
            </div>
            {/* Content */}
            <div className="flex-1 overflow-auto">
              {tab === '🌡️ Market Pulse'  && <MarketPulse/>}
              {tab === '🔍 Screener'      && <Screener/>}
              {tab === '📊 Deep Dive'     && <DeepDive onTickerChange={setDdTicker}/>}
              {tab === '📅 Earnings'      && <Earnings/>}
              {tab === '⚡ Pipeline'      && <Pipeline/>}
              {tab === '🔭 Intel Feed'    && <IntelligenceFeed/>}
              {tab === '💡 Article Ideas' && <ArticleIdeas/>}
            </div>
          </div>

          {/* Right: AI chat */}
          <ChatPanel snapshot={snapshot}/>
        </div>
      </div>
    </QueryClientProvider>
  )
}
