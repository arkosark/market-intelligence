import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'

function FearGauge({ score, rating }: { score: number; rating: string }) {
  const color = score > 65 ? '#ef4444' : score < 35 ? '#10b981' : '#f59e0b'
  const pct = score / 100
  return (
    <div className="card flex flex-col items-center gap-3">
      <span className="text-xs text-[#64748b] uppercase tracking-widest">Semi Fear & Greed</span>
      <div className="relative w-36 h-20">
        <svg viewBox="0 0 140 80" className="w-full h-full">
          {/* Track */}
          <path d="M10,70 A60,60 0 0,1 130,70" fill="none" stroke="#1e2130" strokeWidth="14" strokeLinecap="round"/>
          {/* Fill */}
          <path d="M10,70 A60,60 0 0,1 130,70" fill="none" stroke={color}
            strokeWidth="14" strokeLinecap="round"
            strokeDasharray={`${pct * 188} 188`}/>
          {/* Needle */}
          <line x1="70" y1="70" x2={10 + pct * 120} y2={70 - Math.sin(pct * Math.PI) * 55}
            stroke="white" strokeWidth="2" strokeLinecap="round"/>
          <circle cx="70" cy="70" r="4" fill="white"/>
        </svg>
      </div>
      <div className="text-3xl font-bold font-mono" style={{ color }}>{score}</div>
      <div className="text-xs text-[#94a3b8]">{rating}</div>
    </div>
  )
}

function SectorHeatmap({ data }: { data: any[] }) {
  const getColor = (rsi: number) => rsi > 70 ? '#ef4444' : rsi < 30 ? '#10b981' : '#3b82f6'
  return (
    <div className="card flex-1 min-w-0">
      <div className="text-xs text-[#64748b] uppercase tracking-widest mb-3">Sector RSI Heatmap</div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 20, left: 0 }}>
          <XAxis dataKey="sector" tick={{ fill: '#64748b', fontSize: 10 }} angle={-30} textAnchor="end" interval={0}/>
          <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 10 }} width={28}/>
          <Tooltip
            contentStyle={{ background: '#0f1117', border: '1px solid #1e2130', borderRadius: 6 }}
            formatter={(v: any, _: any, p: any) => [`RSI: ${v} — ${p.payload.signal}`, p.payload.sector]}
          />
          <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3"/>
          <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 3"/>
          <Bar dataKey="rsi" radius={[3, 3, 0, 0]}>
            {data.map((d, i) => <Cell key={i} fill={getColor(d.rsi)}/>)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function PerfBars({ data, field, label }: { data: any[]; field: string; label: string }) {
  const sorted = [...data].sort((a, b) => a[field] - b[field])
  return (
    <div className="card flex-1 min-w-0">
      <div className="text-xs text-[#64748b] uppercase tracking-widest mb-3">{label}</div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={sorted} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 80 }}>
          <XAxis type="number" tick={{ fill: '#64748b', fontSize: 10 }}
            tickFormatter={v => `${v > 0 ? '+' : ''}${v}%`}/>
          <YAxis type="category" dataKey="sector" tick={{ fill: '#94a3b8', fontSize: 10 }} width={76}/>
          <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #1e2130', borderRadius: 6 }}
            formatter={(v: any) => [`${v > 0 ? '+' : ''}${v}%`]}/>
          <ReferenceLine x={0} stroke="#2d2d3d"/>
          <Bar dataKey={field} radius={[0, 3, 3, 0]}>
            {sorted.map((d, i) => <Cell key={i} fill={d[field] >= 0 ? '#10b981' : '#ef4444'}/>)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function MarketPulse() {
  const { data: fg }  = useQuery({ queryKey: ['fg'],      queryFn: api.fearGreed, refetchInterval: 300000 })
  const { data: sec = [] } = useQuery({ queryKey: ['sectors'], queryFn: api.sectors, refetchInterval: 300000 })

  return (
    <div className="flex flex-col gap-4 p-4 overflow-auto">
      {/* Row 1 */}
      <div className="flex gap-4">
        {fg?.score != null && <FearGauge score={fg.score} rating={fg.rating}/>}
        <div className="card flex-1 min-w-0">
          <div className="text-xs text-[#64748b] uppercase tracking-widest mb-3">Sector Signals</div>
          <div className="grid grid-cols-3 gap-2">
            {sec.map((s: any) => (
              <div key={s.sector} className="flex justify-between items-center px-2 py-1 rounded bg-[#0a0a0f]">
                <span className="text-[#94a3b8] text-xs truncate">{s.sector}</span>
                <div className="flex items-center gap-2 ml-2">
                  <span className={`text-xs font-mono ${s.rsi > 70 ? 'signal-overbought' : s.rsi < 30 ? 'signal-oversold' : 'signal-neutral'}`}>
                    {s.rsi}
                  </span>
                  <span className={`text-xs ${s.change1m >= 0 ? 'metric-up' : 'metric-down'}`}>
                    {s.change1m > 0 ? '+' : ''}{s.change1m}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      {/* Row 2: Charts */}
      {sec.length > 0 && (
        <div className="flex gap-4">
          <SectorHeatmap data={sec}/>
          <PerfBars data={sec} field="change1w" label="1-Week Returns"/>
          <PerfBars data={sec} field="change1m" label="1-Month Returns"/>
        </div>
      )}
    </div>
  )
}
