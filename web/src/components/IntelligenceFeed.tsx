import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-[#0f1117] border border-[#1e2130] rounded p-3 text-center">
      <div className="text-xl font-bold text-white">{value}</div>
      <div className="text-[11px] text-[#6b7280] mt-1">{label}</div>
    </div>
  )
}

function RelevanceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 60 ? '#22c55e' : pct >= 30 ? '#f59e0b' : '#6b7280'
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-20 h-1 bg-[#1e2130] rounded overflow-hidden">
        <div style={{ width: `${pct}%`, backgroundColor: color }} className="h-full rounded" />
      </div>
      <span className="text-[10px] text-[#6b7280]">{pct}%</span>
    </div>
  )
}

export default function IntelligenceFeed() {
  const { data, isLoading, refetch } = useQuery({ queryKey: ['feed'], queryFn: api.feed, staleTime: 300000 })

  if (isLoading) return <div className="flex items-center justify-center h-64 text-[#6b7280]">Loading intelligence feed…</div>
  if (!data) return <div className="p-6 text-[#6b7280]">Pipeline not initialised. Run the DeepStack pipeline first.</div>

  const social: any[]   = data.social   || []
  const signals: any[]  = data.signals  || []
  const log: any[]      = data.agent_log || []
  const ingest: any[]   = data.ingest   || []
  const cost            = data.cost

  const xPosts    = social.filter(r => r.source === 'x')
  const reddit    = social.filter(r => r.source === 'reddit')

  return (
    <div className="p-4 space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-5 gap-3">
        <StatCard label="X Posts"        value={xPosts.length} />
        <StatCard label="Reddit Posts"   value={reddit.length} />
        <StatCard label="Signals Queued" value={signals.length} />
        <StatCard label="Pipeline Cost"  value={cost ? `$${cost.total_usd}` : '—'} />
        <StatCard label="Last Run"       value={cost?.last_run?.slice(0,16) || '—'} />
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* X Posts */}
        <div>
          <h3 className="text-sm font-semibold text-[#9ca3af] mb-2 uppercase tracking-wider">𝕏 Posts</h3>
          {xPosts.length === 0
            ? <p className="text-[#4b5563] text-sm">No X posts yet — add credits to X developer account.</p>
            : xPosts.slice(0, 10).map((r: any) => (
              <div key={r.id} className="bg-[#0f1117] border border-[#1e2130] rounded p-3 mb-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-white">@{r.author}</span>
                  <RelevanceBar value={r.relevance} />
                </div>
                <p className="text-xs text-[#d1d5db] line-clamp-3">{r.content}</p>
                {r.tickers && JSON.parse(r.tickers || '[]').length > 0 && (
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {JSON.parse(r.tickers).map((t: string) => (
                      <span key={t} className="text-[10px] bg-[#1e3a5f] text-[#60a5fa] px-1.5 rounded">{t}</span>
                    ))}
                  </div>
                )}
                {r.url && <a href={r.url} target="_blank" rel="noreferrer" className="text-[10px] text-[#6b7280] hover:text-white mt-1 block">Open ↗</a>}
              </div>
            ))
          }
        </div>

        {/* Reddit */}
        <div>
          <h3 className="text-sm font-semibold text-[#9ca3af] mb-2 uppercase tracking-wider">Reddit</h3>
          {reddit.length === 0
            ? <p className="text-[#4b5563] text-sm">No Reddit posts yet — add REDDIT_CLIENT_ID to .env</p>
            : reddit.slice(0, 10).map((r: any) => (
              <div key={r.id} className="bg-[#0f1117] border border-[#1e2130] rounded p-3 mb-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-[#ff4500]">r/{r.subreddit}</span>
                  <RelevanceBar value={r.relevance} />
                </div>
                <p className="text-xs text-[#d1d5db] line-clamp-3">{r.content}</p>
                {r.url && <a href={r.url} target="_blank" rel="noreferrer" className="text-[10px] text-[#6b7280] hover:text-white mt-1 block">Open ↗</a>}
              </div>
            ))
          }
        </div>

        {/* Signal Queue */}
        <div>
          <h3 className="text-sm font-semibold text-[#9ca3af] mb-2 uppercase tracking-wider">Signal Queue</h3>
          {signals.length === 0
            ? <p className="text-[#4b5563] text-sm">No signals queued. Run the pipeline to generate signals.</p>
            : signals.map((s: any) => {
              const score = parseFloat(s.final_score || 0)
              const dot   = score >= 0.8 ? '#22c55e' : score >= 0.6 ? '#f59e0b' : '#ef4444'
              return (
                <div key={s.id} className="bg-[#0f1117] border border-[#1e2130] rounded p-3 mb-2">
                  <div className="flex items-center gap-2 mb-1">
                    <span style={{ color: dot }} className="text-lg leading-none">●</span>
                    <span className="text-xs font-bold text-white">{score.toFixed(2)}</span>
                    <span className="text-[10px] text-[#6b7280]">{s.signal_type}</span>
                  </div>
                  <p className="text-xs text-[#d1d5db] line-clamp-2">{s.hypothesis}</p>
                  <p className="text-[10px] text-[#6b7280] mt-1">{String(s.created_at).slice(0,10)}</p>
                </div>
              )
            })
          }
        </div>
      </div>

      {/* Bottom: Ingest + Agent Log */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h3 className="text-sm font-semibold text-[#9ca3af] mb-2 uppercase tracking-wider">Ingest Status</h3>
          <table className="w-full text-xs">
            <thead><tr className="text-[#6b7280] border-b border-[#1e2130]">
              <th className="text-left py-1">Source</th><th className="text-left py-1">Last Pull</th><th className="text-right py-1">Items</th>
            </tr></thead>
            <tbody>
              {ingest.map((r: any) => (
                <tr key={r.source_key} className="border-b border-[#0f1117] text-[#d1d5db]">
                  <td className="py-1 pr-2 font-mono text-[10px]">{r.source_key}</td>
                  <td className="py-1 pr-2 text-[#6b7280]">{String(r.last_ingested).slice(0,16)}</td>
                  <td className="py-1 text-right">{r.item_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-[#9ca3af] mb-2 uppercase tracking-wider">Agent Activity</h3>
          <table className="w-full text-xs">
            <thead><tr className="text-[#6b7280] border-b border-[#1e2130]">
              <th className="text-left py-1">Time</th><th className="text-left py-1">Action</th><th className="text-left py-1">Entity</th><th className="text-left py-1">Model</th>
            </tr></thead>
            <tbody>
              {log.map((r: any, i: number) => (
                <tr key={i} className="border-b border-[#0f1117] text-[#d1d5db]">
                  <td className="py-1 pr-2 text-[#6b7280]">{String(r.ts).slice(5,16)}</td>
                  <td className="py-1 pr-2">{r.action}</td>
                  <td className="py-1 pr-2 text-[#60a5fa]">{r.entity}</td>
                  <td className="py-1 text-[10px] text-[#9ca3af]">{r.model_tier}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex justify-end">
        <button onClick={() => refetch()} className="text-xs px-3 py-1.5 bg-[#1e2130] hover:bg-[#2d3148] text-[#9ca3af] rounded transition-colors">
          ↻ Refresh
        </button>
      </div>
    </div>
  )
}
