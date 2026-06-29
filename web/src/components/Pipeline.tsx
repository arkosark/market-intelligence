import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

// ── helpers ──────────────────────────────────────────────────────────────────

function score2color(s: number) {
  return s >= 0.8 ? '#22c55e' : s >= 0.6 ? '#f59e0b' : s >= 0.4 ? '#f97316' : '#ef4444'
}

function ScoreBar({ value, max = 1 }: { value: number; max?: number }) {
  const pct = Math.min(100, Math.round((value / max) * 100))
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 bg-[#1e2130] rounded overflow-hidden">
        <div style={{ width: `${pct}%`, backgroundColor: score2color(value / max) }} className="h-full" />
      </div>
      <span className="text-[10px] tabular-nums" style={{ color: score2color(value / max) }}>
        {value.toFixed(2)}
      </span>
    </div>
  )
}

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded font-mono" style={{ background: color + '22', color }}>
      {label}
    </span>
  )
}

// ── Pipeline stage data comes from /api/pipeline ─────────────────────────────

export default function Pipeline() {
  const [sigTab, setSigTab] = useState<'queued' | 'all'>('queued')
  const [expandedSig, setExpandedSig] = useState<string | null>(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['pipeline'],
    queryFn: api.pipeline,
    staleTime: 60000,
  })

  if (isLoading) return (
    <div className="flex items-center justify-center h-64 text-[#6b7280]">Loading pipeline…</div>
  )
  if (!data) return (
    <div className="p-6 text-[#6b7280]">Pipeline DB not found. Run DeepStack first.</div>
  )

  const stages: any[]   = data.stages   || []
  const signals: any[]  = data.signals  || []
  const earnings: any[] = data.earnings || []
  const costs: any[]    = data.costs    || []
  const ingest: any[]   = data.ingest   || []

  const visibleSigs = sigTab === 'queued'
    ? signals.filter((s: any) => s.status === 'queued')
    : signals

  const totalCost = costs.reduce((a: number, r: any) => a + (r.cost_usd || 0), 0)

  return (
    <div className="p-4 space-y-5">

      {/* ── Stage tracker ─────────────────────────────────────── */}
      <section>
        <h3 className="text-xs font-semibold text-[#6b7280] uppercase tracking-wider mb-3">Pipeline Stages</h3>
        <div className="flex gap-2 items-stretch">
          {stages.map((st: any, i: number) => (
            <div key={st.name} className="flex items-center gap-2 flex-1">
              <div className={`flex-1 rounded p-3 border ${st.active ? 'border-[#374151] bg-[#111827]' : 'border-[#1e2130] bg-[#0a0a0f]'}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-base">{st.icon}</span>
                  <span className="text-xs font-semibold text-white">{st.name}</span>
                  <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${
                    st.status === 'ok'      ? 'bg-[#14532d] text-[#22c55e]' :
                    st.status === 'running' ? 'bg-[#1e3a5f] text-[#60a5fa]' :
                    st.status === 'warn'    ? 'bg-[#451a03] text-[#f59e0b]' :
                                             'bg-[#1e2130] text-[#6b7280]'
                  }`}>{st.status}</span>
                </div>
                <p className="text-[11px] text-[#6b7280]">{st.detail}</p>
              </div>
              {i < stages.length - 1 && (
                <span className="text-[#374151] text-lg flex-shrink-0">→</span>
              )}
            </div>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-3 gap-4">

        {/* ── Signal Queue ──────────────────────────────────── */}
        <div className="col-span-2">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-[#6b7280] uppercase tracking-wider">Signals</h3>
            <div className="flex gap-1">
              {(['queued', 'all'] as const).map(t => (
                <button key={t} onClick={() => setSigTab(t)}
                  className={`text-[10px] px-2 py-0.5 rounded capitalize ${sigTab === t ? 'bg-[#2d3148] text-white' : 'text-[#6b7280] hover:text-white'}`}>
                  {t} {t === 'queued' ? `(${signals.filter((s:any)=>s.status==='queued').length})` : `(${signals.length})`}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-auto max-h-[420px] space-y-1.5">
            {visibleSigs.length === 0
              ? <p className="text-[#4b5563] text-sm p-4">No signals. Run pipeline to generate.</p>
              : visibleSigs.map((s: any) => {
                const score  = parseFloat(s.final_score || 0)
                const isOpen = expandedSig === s.id
                const tickers: string[] = JSON.parse(s.tickers_json || '[]')
                return (
                  <div key={s.id}
                    className="bg-[#0f1117] border border-[#1e2130] rounded overflow-hidden hover:border-[#374151] transition-colors cursor-pointer"
                    onClick={() => setExpandedSig(isOpen ? null : s.id)}>
                    {/* row */}
                    <div className="flex items-center gap-3 px-3 py-2">
                      <div className="w-1.5 h-8 rounded-full flex-shrink-0" style={{ backgroundColor: score2color(score) }} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-white truncate">{s.hypothesis}</p>
                        <div className="flex gap-2 mt-0.5 flex-wrap">
                          <Pill label={s.signal_type} color="#60a5fa" />
                          {tickers.slice(0,3).map((t:string) => <Pill key={t} label={t} color="#a78bfa" />)}
                          <span className="text-[10px] text-[#6b7280]">{String(s.created_at).slice(0,10)}</span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1 flex-shrink-0">
                        <ScoreBar value={score} />
                        <span className="text-[10px] text-[#6b7280]">{s.status}</span>
                      </div>
                      <span className="text-[#374151] text-xs ml-1">{isOpen ? '▲' : '▼'}</span>
                    </div>
                    {/* expanded */}
                    {isOpen && (
                      <div className="px-3 pb-3 border-t border-[#1e2130] pt-2 space-y-2">
                        {s.expected_outcome && (
                          <div>
                            <p className="text-[10px] text-[#6b7280] uppercase mb-0.5">Expected outcome</p>
                            <p className="text-xs text-[#d1d5db]">{s.expected_outcome}</p>
                          </div>
                        )}
                        <div className="grid grid-cols-4 gap-2">
                          {[
                            { label: 'Novelty',     v: s.novelty },
                            { label: 'Magnitude',   v: s.magnitude },
                            { label: 'Confirmation',v: s.confirmation },
                            { label: 'Consensus Δ', v: s.consensus_divergence },
                          ].filter(d => d.v != null).map(d => (
                            <div key={d.label} className="bg-[#0a0a0f] rounded p-2 text-center">
                              <p className="text-[10px] text-[#6b7280]">{d.label}</p>
                              <ScoreBar value={parseFloat(d.v)} />
                            </div>
                          ))}
                        </div>
                        {s.evidence && (
                          <div>
                            <p className="text-[10px] text-[#6b7280] uppercase mb-0.5">Evidence</p>
                            <p className="text-xs text-[#9ca3af] line-clamp-3">{s.evidence}</p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })
            }
          </div>
        </div>

        {/* ── Right col: Earnings + Cost ─────────────────────── */}
        <div className="space-y-4">

          {/* Earnings calendar */}
          <div>
            <h3 className="text-xs font-semibold text-[#6b7280] uppercase tracking-wider mb-2">Earnings Dates</h3>
            <div className="space-y-1 max-h-[200px] overflow-auto">
              {earnings.length === 0
                ? <p className="text-[#4b5563] text-xs">No upcoming earnings loaded.</p>
                : earnings.map((e: any) => {
                  const hasSignal = signals.some((s:any) =>
                    JSON.parse(s.tickers_json || '[]').includes(e.ticker)
                  )
                  return (
                    <div key={e.id} className={`flex items-center gap-2 px-2 py-1.5 rounded ${hasSignal ? 'bg-[#1e3a5f]' : 'bg-[#0f1117]'}`}>
                      <span className="text-[11px] font-bold text-white w-12 flex-shrink-0">{e.ticker}</span>
                      <span className="text-[10px] text-[#9ca3af] flex-1 truncate">{e.event_name || e.event_type}</span>
                      <span className="text-[10px] text-[#6b7280] flex-shrink-0">{String(e.event_date).slice(0,10)}</span>
                      {hasSignal && <span className="text-[10px] text-[#60a5fa]">●</span>}
                    </div>
                  )
                })
              }
            </div>
            {earnings.length > 0 && (
              <p className="text-[10px] text-[#374151] mt-1">● = active signal for this ticker</p>
            )}
          </div>

          {/* Ingest status */}
          <div>
            <h3 className="text-xs font-semibold text-[#6b7280] uppercase tracking-wider mb-2">Ingest</h3>
            <div className="space-y-1">
              {ingest.slice(0,8).map((r: any) => {
                const age = r.last_ingested
                  ? Math.round((Date.now() - new Date(r.last_ingested).getTime()) / 60000)
                  : null
                const stale = age != null && age > 120
                return (
                  <div key={r.source_key} className="flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${stale ? 'bg-[#f59e0b]' : 'bg-[#22c55e]'}`} />
                    <span className="text-[10px] font-mono text-[#9ca3af] flex-1 truncate">{r.source_key}</span>
                    <span className="text-[10px] text-[#6b7280]">{age != null ? `${age}m ago` : '—'}</span>
                    <span className="text-[10px] text-[#374151]">{r.item_count}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Cost */}
          <div>
            <h3 className="text-xs font-semibold text-[#6b7280] uppercase tracking-wider mb-2">API Cost</h3>
            <div className="bg-[#0f1117] border border-[#1e2130] rounded p-3 text-center mb-2">
              <p className="text-2xl font-bold text-white">${totalCost.toFixed(4)}</p>
              <p className="text-[10px] text-[#6b7280] mt-1">total across {costs.length} cycle{costs.length !== 1 ? 's' : ''}</p>
            </div>
            <div className="space-y-1 max-h-[120px] overflow-auto">
              {costs.slice(0,10).map((r: any, i: number) => (
                <div key={i} className="flex items-center gap-2 text-[10px]">
                  <span className="text-[#6b7280] w-32 truncate">{String(r.cycle_ts).slice(0,16)}</span>
                  <span className="text-[#9ca3af] flex-1">{r.model?.split('-').pop()}</span>
                  <span className="text-white tabular-nums">${parseFloat(r.cost_usd||0).toFixed(4)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <button onClick={() => refetch()}
          className="text-xs px-3 py-1.5 bg-[#1e2130] hover:bg-[#2d3148] text-[#9ca3af] rounded transition-colors">
          ↻ Refresh
        </button>
      </div>
    </div>
  )
}
