import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, ZAxis } from 'recharts'

export default function Screener() {
  const { data: rows = [], isLoading } = useQuery({ queryKey: ['screener'], queryFn: api.screener, staleTime: 900000 })
  const [sector, setSector] = useState('All')
  const [minScore, setMinScore] = useState(2)
  const [maxRsi, setMaxRsi] = useState(80)
  const [minRsi, setMinRsi] = useState(20)
  const [sortBy, setSortBy] = useState('score')

  const sectors = ['All', ...Array.from(new Set(rows.map((r: any) => r.sector))).sort()]
  const filtered = rows
    .filter((r: any) => (sector === 'All' || r.sector === sector) && r.rsi >= minRsi && r.rsi <= maxRsi && r.score >= minScore)
    .sort((a: any, b: any) => (b[sortBy] ?? 0) - (a[sortBy] ?? 0))

  const bubbleData = rows
    .filter((r: any) => r.pe && r.epsGrowth)
    .map((r: any) => ({ ...r, z: Math.max(1, (r.marketCap || 0) / 1e10) }))

  const rsiCell = (v: number) => v > 70 ? 'rsi-high' : v < 30 ? 'rsi-low' : ''
  const scoreCell = (v: number) => v >= 5 ? 'score-high' : v >= 3 ? 'score-mid' : ''

  return (
    <div className="flex flex-col gap-4 p-4 overflow-auto">
      {/* Filters */}
      <div className="card flex flex-wrap gap-4 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#64748b]">Sector</label>
          <select value={sector} onChange={e => setSector(e.target.value)}
            className="bg-[#0a0a0f] border border-[#1e2130] rounded px-2 py-1 text-sm text-[#e2e8f0]">
            {(sectors as string[]).map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#64748b]">RSI {minRsi}–{maxRsi}</label>
          <div className="flex gap-2">
            <input type="range" min={0} max={100} value={minRsi} onChange={e => setMinRsi(+e.target.value)} className="w-20"/>
            <input type="range" min={0} max={100} value={maxRsi} onChange={e => setMaxRsi(+e.target.value)} className="w-20"/>
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#64748b]">Min Score: {minScore}</label>
          <input type="range" min={0} max={6} value={minScore} onChange={e => setMinScore(+e.target.value)} className="w-32"/>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#64748b]">Sort by</label>
          <select value={sortBy} onChange={e => setSortBy(e.target.value)}
            className="bg-[#0a0a0f] border border-[#1e2130] rounded px-2 py-1 text-sm text-[#e2e8f0]">
            <option value="score">Score</option>
            <option value="rsi">RSI</option>
            <option value="change1m">1M %</option>
            <option value="pe">P/E</option>
            <option value="epsGrowth">EPS Growth</option>
          </select>
        </div>
        <span className="text-xs text-[#64748b]">{filtered.length} stocks</span>
      </div>

      {isLoading ? (
        <div className="text-[#64748b] text-sm p-8 text-center">Loading screener (~30s)…</div>
      ) : (
        <div className="card overflow-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[#64748b] border-b border-[#1e2130]">
                {['Ticker','Sector','Price','RSI','P/E','Fwd P/E','EPS%','Rev%','GM%','1M%','>MA50','Score'].map(h => (
                  <th key={h} className="text-left py-2 px-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r: any) => (
                <tr key={r.ticker} className="border-b border-[#0a0a0f] hover:bg-[#1a1a2e] transition-colors">
                  <td className="py-1.5 px-2 font-bold text-[#3b82f6]">{r.ticker}</td>
                  <td className="py-1.5 px-2 text-[#94a3b8]">{r.sector}</td>
                  <td className="py-1.5 px-2 font-mono">${r.price}</td>
                  <td className={`py-1.5 px-2 font-mono rounded ${rsiCell(r.rsi)}`}>{r.rsi}</td>
                  <td className="py-1.5 px-2 font-mono">{r.pe ?? '—'}</td>
                  <td className="py-1.5 px-2 font-mono">{r.fwdPe ?? '—'}</td>
                  <td className={`py-1.5 px-2 font-mono ${r.epsGrowth > 0 ? 'metric-up' : r.epsGrowth < 0 ? 'metric-down' : ''}`}>{r.epsGrowth != null ? `${r.epsGrowth}%` : '—'}</td>
                  <td className={`py-1.5 px-2 font-mono ${r.revGrowth > 0 ? 'metric-up' : ''}`}>{r.revGrowth != null ? `${r.revGrowth}%` : '—'}</td>
                  <td className="py-1.5 px-2 font-mono">{r.grossMargin != null ? `${r.grossMargin}%` : '—'}</td>
                  <td className={`py-1.5 px-2 font-mono ${r.change1m >= 0 ? 'metric-up' : 'metric-down'}`}>{r.change1m > 0 ? '+' : ''}{r.change1m}%</td>
                  <td className="py-1.5 px-2">{r.aboveMa50 ? '✅' : '❌'}</td>
                  <td className={`py-1.5 px-2 font-bold rounded ${scoreCell(r.score)}`}>{r.score}/6</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Bubble chart */}
      <div className="card">
        <div className="text-xs text-[#64748b] uppercase tracking-widest mb-3">Opportunity Map — P/E vs EPS Growth (bubble = market cap)</div>
        <ResponsiveContainer width="100%" height={340}>
          <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 20 }}>
            <XAxis dataKey="pe" name="P/E" type="number" domain={[0, 80]}
              tick={{ fill: '#64748b', fontSize: 10 }} label={{ value: 'Trailing P/E', position: 'insideBottom', offset: -10, fill: '#64748b', fontSize: 11 }}/>
            <YAxis dataKey="epsGrowth" name="EPS Growth %" type="number"
              tick={{ fill: '#64748b', fontSize: 10 }} label={{ value: 'EPS Growth %', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }}/>
            <ZAxis dataKey="z" range={[40, 800]}/>
            <Tooltip cursor={{ stroke: '#2d2d3d' }}
              contentStyle={{ background: '#0f1117', border: '1px solid #1e2130', borderRadius: 6 }}
              content={({ payload }) => {
                if (!payload?.length) return null
                const d = payload[0].payload
                return (
                  <div className="text-xs p-2">
                    <div className="font-bold text-[#3b82f6]">{d.ticker}</div>
                    <div className="text-[#94a3b8]">{d.sector}</div>
                    <div>P/E: {d.pe} | EPS: {d.epsGrowth}%</div>
                    <div>RSI: {d.rsi} | Score: {d.score}/6</div>
                  </div>
                )
              }}/>
            <ReferenceLine x={25} stroke="#2d2d3d" strokeDasharray="4 2"/>
            <ReferenceLine y={10} stroke="#2d2d3d" strokeDasharray="4 2"/>
            <Scatter data={bubbleData} fill="#3b82f6" fillOpacity={0.7}/>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
