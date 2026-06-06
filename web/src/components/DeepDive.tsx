import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import {
  ComposedChart, Line, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Area, Cell
} from 'recharts'
import { createChart, ColorType, CandlestickSeries, LineSeries } from 'lightweight-charts'
import { useEffect, useRef } from 'react'

const PERIODS = ['1 Week','3 Weeks','1 Month','3 Months','6 Months','1 Year','2 Years']
const PERIOD_MAP: Record<string, [string, number | null]> = {
  '1 Week':   ['5d',  null],
  '3 Weeks':  ['1mo', 15],
  '1 Month':  ['1mo', null],
  '3 Months': ['3mo', null],
  '6 Months': ['6mo', null],
  '1 Year':   ['1y',  null],
  '2 Years':  ['2y',  null],
}

function CandleChart({ candles, indicators }: { candles: any[]; indicators: any }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current || !candles.length) return

    const chart = createChart(ref.current, {
      layout: { background: { type: ColorType.Solid, color: '#0f1117' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e2130' }, horzLines: { color: '#1e2130' } },
      rightPriceScale: { borderColor: '#1e2130' },
      timeScale: { borderColor: '#1e2130', timeVisible: true },
      width: ref.current.clientWidth,
      height: 340,
    })

    // v5 API: chart.addSeries(SeriesType, options)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981', downColor: '#ef4444',
      borderUpColor: '#10b981', borderDownColor: '#ef4444',
      wickUpColor: '#10b981', wickDownColor: '#ef4444',
    })
    candleSeries.setData(candles.map((c: any) => ({
      time: c.t as any, open: c.o, high: c.h, low: c.l, close: c.c,
    })))

    const toSeries = (key: string) =>
      (indicators?.[key] ?? []).filter((d: any) => d.v != null).map((d: any) => ({ time: d.t as any, value: d.v }))

    if (indicators?.ma50?.length) {
      chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1 as any }).setData(toSeries('ma50'))
    }
    if (indicators?.ma200?.length) {
      chart.addSeries(LineSeries, { color: '#8b5cf6', lineWidth: 1 as any }).setData(toSeries('ma200'))
    }
    if (indicators?.bbUpper?.length) {
      chart.addSeries(LineSeries, { color: 'rgba(100,149,237,0.45)', lineWidth: 1 as any, lineStyle: 2 as any }).setData(toSeries('bbUpper'))
      chart.addSeries(LineSeries, { color: 'rgba(100,149,237,0.45)', lineWidth: 1 as any, lineStyle: 2 as any }).setData(toSeries('bbLower'))
    }

    chart.timeScale().fitContent()

    const ro = new ResizeObserver(() => {
      if (ref.current) chart.applyOptions({ width: ref.current.clientWidth })
    })
    ro.observe(ref.current)
    return () => { chart.remove(); ro.disconnect() }
  }, [candles, indicators])

  return <div ref={ref} className="w-full rounded"/>
}

function SubChart({ data, dataKey, color, label, refLines = [], fill = false }: any) {
  return (
    <div className="card">
      <div className="text-xs text-[#64748b] mb-2">{label}</div>
      <ResponsiveContainer width="100%" height={100}>
        <ComposedChart data={data} margin={{ top: 2, right: 4, bottom: 2, left: 0 }}>
          <XAxis dataKey="t" hide/>
          <YAxis tick={{ fill: '#64748b', fontSize: 9 }} width={36}/>
          <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #1e2130', borderRadius: 4, fontSize: 11 }}/>
          {refLines.map((y: number) => <ReferenceLine key={y} y={y} stroke={y > 0 ? '#ef4444' : '#10b981'} strokeDasharray="3 3"/>)}
          {fill
            ? <Area type="monotone" dataKey={dataKey} stroke={color} fill={color} fillOpacity={0.1} dot={false} strokeWidth={1.5}/>
            : <Line type="monotone" dataKey={dataKey} stroke={color} dot={false} strokeWidth={1.5}/>}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function MACDChart({ data }: { data: any[] }) {
  return (
    <div className="card">
      <div className="text-xs text-[#64748b] mb-2">MACD (12/26/9)</div>
      <ResponsiveContainer width="100%" height={100}>
        <ComposedChart data={data} margin={{ top: 2, right: 4, bottom: 2, left: 0 }}>
          <XAxis dataKey="t" hide/>
          <YAxis tick={{ fill: '#64748b', fontSize: 9 }} width={36}/>
          <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #1e2130', borderRadius: 4, fontSize: 11 }}/>
          <ReferenceLine y={0} stroke="#2d2d3d"/>
          <Bar dataKey="hist">
            {data.map((d, i) => <Cell key={i} fill={d.hist >= 0 ? '#10b981' : '#ef4444'}/>)}
          </Bar>
          <Line type="monotone" dataKey="macd" stroke="#3b82f6" dot={false} strokeWidth={1.5}/>
          <Line type="monotone" dataKey="signal" stroke="#ef4444" dot={false} strokeWidth={1.5}/>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function CMFChart({ data }: { data: any[] }) {
  return (
    <div className="card">
      <div className="text-xs text-[#64748b] mb-2">CMF — Chaikin Money Flow &nbsp;<span className="text-[#10b981]">+ve = Accumulation</span> / <span className="text-[#ef4444]">−ve = Distribution</span></div>
      <ResponsiveContainer width="100%" height={100}>
        <ComposedChart data={data} margin={{ top: 2, right: 4, bottom: 2, left: 0 }}>
          <XAxis dataKey="t" hide/>
          <YAxis tick={{ fill: '#64748b', fontSize: 9 }} width={36} tickFormatter={v => v.toFixed(2)}/>
          <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #1e2130', borderRadius: 4, fontSize: 11 }}
            formatter={(v: any) => [v?.toFixed ? v.toFixed(3) : v, 'CMF']}/>
          <ReferenceLine y={0} stroke="#2d2d3d"/>
          <ReferenceLine y={0.05}  stroke="#10b981" strokeDasharray="2 2"/>
          <ReferenceLine y={-0.05} stroke="#ef4444" strokeDasharray="2 2"/>
          <Bar dataKey="cmf">
            {data.map((d, i) => <Cell key={i} fill={d.cmf >= 0 ? '#10b981' : '#ef4444'}/>)}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function Metric({ label, value, sub, color }: any) {
  return (
    <div className="card text-center">
      <div className="text-[10px] text-[#64748b] uppercase mb-1">{label}</div>
      <div className="text-lg font-bold font-mono" style={{ color }}>{value}</div>
      {sub && <div className="text-[10px] mt-0.5" style={{ color }}>{sub}</div>}
    </div>
  )
}

export default function DeepDive({ onTickerChange }: { onTickerChange: (t: string) => void }) {
  const [ticker, setTicker] = useState('NVDA')
  const [input, setInput] = useState('NVDA')
  const [period, setPeriod] = useState('6 Months')
  const [yf_period, sliceRows] = PERIOD_MAP[period]

  const { data, isLoading } = useQuery({
    queryKey: ['stock', ticker, yf_period],
    queryFn: () => api.stock(ticker, yf_period),
    staleTime: 900000,
    enabled: !!ticker,
  })
  const { data: inst } = useQuery({
    queryKey: ['inst', ticker],
    queryFn: () => api.institutional(ticker),
    staleTime: 3600000,
    enabled: !!ticker,
  })

  const candles = sliceRows ? (data?.candles ?? []).slice(-sliceRows) : (data?.candles ?? [])
  const slice = (key: string) => {
    const arr = data?.indicators?.[key] ?? []
    return sliceRows ? arr.slice(-sliceRows) : arr
  }

  const rsiData  = slice('rsi').map((d: any) => ({ t: d.t, rsi: d.v }))
  const macdData = slice('macd').map((d: any, i: number) => ({
    t: d.t, macd: d.v,
    signal: slice('macdSignal')[i]?.v,
    hist:   slice('macdHist')[i]?.v,
  }))
  const cmfData  = slice('cmf').map((d: any) => ({ t: d.t, cmf: d.v }))
  const mfiData  = slice('mfi').map((d: any) => ({ t: d.t, mfi: d.v }))
  const obvData  = slice('obv').map((d: any) => ({ t: d.t, obv: d.v }))

  const curRsi = rsiData.at(-1)?.rsi
  const curCmf = cmfData.at(-1)?.cmf
  const curMfi = mfiData.at(-1)?.mfi
  const obvNow = obvData.at(-1)?.obv; const obv5 = obvData.at(-6)?.obv
  const obvTrend = obvNow != null && obv5 != null ? (obvNow > obv5 ? 'Rising ↑' : 'Falling ↓') : '—'

  const info = data?.info ?? {}

  const fmt = (v: any, pct = false) => v == null ? '—' : pct ? `${(v * 100).toFixed(1)}%` : v

  function handleLoad() {
    const t = input.trim().toUpperCase()
    if (t) { setTicker(t); onTickerChange(t) }
  }

  return (
    <div className="flex flex-col gap-3 p-4 overflow-auto">
      {/* Controls */}
      <div className="flex gap-3 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#64748b]">Ticker</label>
          <input value={input} onChange={e => setInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleLoad()}
            className="bg-[#0a0a0f] border border-[#1e2130] rounded px-3 py-1.5 text-sm font-mono w-28 text-[#e2e8f0] focus:outline-none focus:border-[#3b82f6]"/>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#64748b]">Period</label>
          <select value={period} onChange={e => setPeriod(e.target.value)}
            className="bg-[#0a0a0f] border border-[#1e2130] rounded px-2 py-1.5 text-sm text-[#e2e8f0]">
            {PERIODS.map(p => <option key={p}>{p}</option>)}
          </select>
        </div>
        <button onClick={handleLoad}
          className="px-4 py-1.5 bg-[#3b82f6] hover:bg-[#2563eb] text-white rounded text-sm font-medium transition-colors">
          Load
        </button>
        {data && <span className="text-xs text-[#64748b] self-end pb-1">
          {info.longName || ticker} · {info.sector}
        </span>}
      </div>

      {isLoading && <div className="text-[#64748b] text-sm p-8 text-center">Loading {ticker}…</div>}

      {data && !isLoading && (
        <>
          {/* Metrics */}
          <div className="grid grid-cols-7 gap-2">
            <Metric label="Price" value={`$${data.price}`}
              sub={`${data.change >= 0 ? '+' : ''}${data.change}%`}
              color={data.change >= 0 ? '#10b981' : '#ef4444'}/>
            <Metric label="Mkt Cap" value={info.marketCap ? `$${(info.marketCap/1e9).toFixed(1)}B` : '—'} color="#e2e8f0"/>
            <Metric label="P/E" value={info.trailingPE?.toFixed(1) ?? '—'} color="#e2e8f0"/>
            <Metric label="Fwd P/E" value={info.forwardPE?.toFixed(1) ?? '—'} color="#e2e8f0"/>
            <Metric label="52W High" value={`$${info.fiftyTwoWeekHigh ?? '—'}`} color="#e2e8f0"/>
            <Metric label="52W Low" value={`$${info.fiftyTwoWeekLow ?? '—'}`} color="#e2e8f0"/>
            <Metric label="Beta" value={info.beta?.toFixed(2) ?? '—'} color="#e2e8f0"/>
          </div>

          {/* Candle chart */}
          <div className="card">
            <div className="text-xs text-[#64748b] uppercase tracking-widest mb-2">{ticker} · Price + MA50/200 + Bollinger</div>
            <CandleChart candles={candles} indicators={data.indicators}/>
          </div>

          {/* Sub-charts */}
          <div className="grid grid-cols-2 gap-3">
            <SubChart data={rsiData} dataKey="rsi" color="#8b5cf6" label="RSI (14)" refLines={[70, 30]} fill/>
            <SubChart data={mfiData} dataKey="mfi" color="#3b82f6" label="MFI — Money Flow Index (14)" refLines={[80, 20]} fill/>
          </div>
          <CMFChart data={cmfData}/>
          <SubChart data={obvData} dataKey="obv" color="#f59e0b" label="OBV — On Balance Volume" fill/>
          <MACDChart data={macdData}/>

          {/* Flow signal summary */}
          <div className="grid grid-cols-4 gap-2">
            <Metric label="RSI" value={curRsi?.toFixed(1) ?? '—'}
              sub={curRsi > 70 ? 'Overbought' : curRsi < 30 ? 'Oversold' : 'Neutral'}
              color={curRsi > 70 ? '#ef4444' : curRsi < 30 ? '#10b981' : '#64748b'}/>
            <Metric label="MFI" value={curMfi?.toFixed(1) ?? '—'}
              sub={curMfi > 80 ? 'Sell pressure' : curMfi < 20 ? 'Buy pressure' : 'Neutral'}
              color={curMfi > 80 ? '#ef4444' : curMfi < 20 ? '#10b981' : '#64748b'}/>
            <Metric label="CMF (Smart Money)" value={curCmf?.toFixed(3) ?? '—'}
              sub={curCmf > 0.05 ? 'Accumulating ✅' : curCmf < -0.05 ? 'Distributing ⚠️' : 'Neutral'}
              color={curCmf > 0.05 ? '#10b981' : curCmf < -0.05 ? '#ef4444' : '#64748b'}/>
            <Metric label="OBV Trend" value={obvTrend}
              color={obvTrend.includes('↑') ? '#10b981' : '#ef4444'}/>
          </div>

          {/* Fundamentals */}
          <div className="grid grid-cols-2 gap-4">
            <div className="card">
              <div className="text-xs text-[#64748b] uppercase tracking-widest mb-3">Fundamentals</div>
              <table className="w-full text-xs">
                <tbody>
                  {[
                    ['EPS Growth', fmt(info.earningsGrowth, true)],
                    ['Revenue Growth', fmt(info.revenueGrowth, true)],
                    ['Gross Margin', fmt(info.grossMargins, true)],
                    ['Operating Margin', fmt(info.operatingMargins, true)],
                    ['Net Margin', fmt(info.profitMargins, true)],
                    ['Debt / Equity', fmt(info.debtToEquity)],
                  ].map(([k,v]) => (
                    <tr key={k} className="border-b border-[#0a0a0f]">
                      <td className="py-1.5 text-[#64748b]">{k}</td>
                      <td className="py-1.5 font-mono text-right">{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card">
              <div className="text-xs text-[#64748b] uppercase tracking-widest mb-3">Returns & Valuation</div>
              <table className="w-full text-xs">
                <tbody>
                  {[
                    ['Return on Equity', fmt(info.returnOnEquity, true)],
                    ['Return on Assets', fmt(info.returnOnAssets, true)],
                    ['Free Cash Flow', info.freeCashflow ? `$${(info.freeCashflow/1e9).toFixed(2)}B` : '—'],
                    ['Current Ratio', fmt(info.currentRatio)],
                    ['Analyst Target', info.targetMeanPrice ? `$${info.targetMeanPrice}` : '—'],
                    ['Dividend Yield', fmt(info.dividendYield, true)],
                  ].map(([k,v]) => (
                    <tr key={k} className="border-b border-[#0a0a0f]">
                      <td className="py-1.5 text-[#64748b]">{k}</td>
                      <td className="py-1.5 font-mono text-right">{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Institutional */}
          {inst && (
            <div className="grid grid-cols-2 gap-4">
              {inst.majorHolders && (
                <div className="card">
                  <div className="text-xs text-[#64748b] uppercase tracking-widest mb-3">Ownership Breakdown</div>
                  <table className="w-full text-xs">
                    <tbody>
                      {inst.majorHolders.map((r: any, i: number) => (
                        <tr key={i} className="border-b border-[#0a0a0f]">
                          <td className="py-1.5 text-[#64748b]">{r.description}</td>
                          <td className="py-1.5 font-mono text-right">{r.value}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {inst.institutionalHolders && (
                <div className="card overflow-auto">
                  <div className="text-xs text-[#64748b] uppercase tracking-widest mb-3">Top Institutional Holders <span className="text-[#2d2d3d] normal-case">(13F quarterly)</span></div>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-[#64748b] border-b border-[#1e2130]">
                        <th className="text-left py-1.5">Holder</th>
                        <th className="text-right py-1.5">Shares</th>
                        <th className="text-right py-1.5">% Held</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inst.institutionalHolders.map((r: any, i: number) => (
                        <tr key={i} className="border-b border-[#0a0a0f]">
                          <td className="py-1.5 text-[#94a3b8] truncate max-w-[160px]">{r.Holder}</td>
                          <td className="py-1.5 font-mono text-right">{r.Shares?.toLocaleString()}</td>
                          <td className="py-1.5 font-mono text-right">{r.pctHeld ? `${(r.pctHeld*100).toFixed(2)}%` : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
