import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'

type SourceFilter = 'all' | 'substack' | 'ideas'

function RelevanceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 60 ? '#22c55e' : pct >= 30 ? '#f59e0b' : '#6b7280'
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1 bg-[#1e2130] rounded overflow-hidden">
        <div style={{ width: `${pct}%`, backgroundColor: color }} className="h-full" />
      </div>
      <span className="text-[10px] text-[#6b7280]">{pct}%</span>
    </div>
  )
}

function TickerBadge({ ticker }: { ticker: string }) {
  return (
    <span className="text-[10px] bg-[#1e3a5f] text-[#60a5fa] px-1.5 py-0.5 rounded font-mono">
      {ticker}
    </span>
  )
}

function SubstackCard({ item, onSave }: { item: any; onSave: (item: any) => void }) {
  const [saved, setSaved] = useState(false)
  return (
    <div className="bg-[#0f1117] border border-[#1e2130] rounded p-3 mb-2 hover:border-[#374151] transition-colors">
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-white truncate">{item.title}</p>
          <p className="text-[10px] text-[#60a5fa] mt-0.5">{item.source_name} · {item.published}</p>
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <RelevanceBar value={item.relevance} />
        </div>
      </div>
      {item.summary && (
        <p className="text-[11px] text-[#9ca3af] line-clamp-2 mb-2">{item.summary}</p>
      )}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 flex-wrap">
          {item.tickers?.slice(0, 4).map((t: string) => <TickerBadge key={t} ticker={t} />)}
        </div>
        <div className="flex gap-2">
          {item.url && (
            <a href={item.url} target="_blank" rel="noreferrer"
               className="text-[10px] text-[#6b7280] hover:text-[#9ca3af]">
              Read ↗
            </a>
          )}
          <button
            onClick={() => { onSave(item); setSaved(true) }}
            disabled={saved}
            className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
              saved
                ? 'bg-[#1a2e1a] text-[#22c55e] cursor-default'
                : 'bg-[#1e2130] hover:bg-[#2d3148] text-[#9ca3af] hover:text-white'
            }`}>
            {saved ? '✓ Saved' : '+ Save Idea'}
          </button>
        </div>
      </div>
    </div>
  )
}

function IdeasCard({ item, onStatus }: { item: any; onStatus: (id: string, s: string) => void }) {
  const statusColors: Record<string, string> = {
    new: 'text-[#60a5fa]',
    writing: 'text-[#f59e0b]',
    published: 'text-[#22c55e]',
    dismissed: 'text-[#6b7280]',
  }
  return (
    <div className="bg-[#0f1117] border border-[#1e2130] rounded p-3 mb-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-white">{item.title || item.summary?.slice(0, 80)}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className={`text-[10px] font-bold uppercase ${statusColors[item.status] || 'text-[#9ca3af]'}`}>
              {item.status}
            </span>
            <span className="text-[10px] text-[#6b7280]">{item.created_at}</span>
          </div>
        </div>
        <RelevanceBar value={item.relevance} />
      </div>
      {item.summary && (
        <p className="text-[11px] text-[#9ca3af] line-clamp-2 mt-1">{item.summary}</p>
      )}
      <div className="flex items-center justify-between mt-2">
        <div className="flex gap-1 flex-wrap">
          {item.tickers?.slice(0, 4).map((t: string) => <TickerBadge key={t} ticker={t} />)}
        </div>
        <div className="flex gap-1">
          {item.status === 'new' && (
            <button onClick={() => onStatus(item.id, 'writing')}
              className="text-[10px] px-2 py-0.5 rounded bg-[#1e2130] hover:bg-[#f59e0b] hover:text-black text-[#9ca3af] transition-colors">
              ✍️ Writing
            </button>
          )}
          {item.status === 'writing' && (
            <button onClick={() => onStatus(item.id, 'published')}
              className="text-[10px] px-2 py-0.5 rounded bg-[#1e2130] hover:bg-[#22c55e] hover:text-black text-[#9ca3af] transition-colors">
              ✅ Published
            </button>
          )}
          <button onClick={() => onStatus(item.id, 'dismissed')}
            className="text-[10px] px-2 py-0.5 rounded bg-[#1e2130] hover:bg-[#ef4444] hover:text-white text-[#6b7280] transition-colors">
            ✕
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ArticleIdeas() {
  const [filter, setFilter] = useState<SourceFilter>('all')
  const qc = useQueryClient()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['ideas'],
    queryFn: api.ideas,
    staleTime: 3600000,
  })

  const saveMut = useMutation({
    mutationFn: (item: any) => api.saveIdea({
      origin_id:   item.id,
      origin_type: item.type || 'substack',
      title:       item.title,
      summary:     item.summary,
      url:         item.url,
      tickers:     item.tickers,
      relevance:   item.relevance,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ideas'] }),
  })

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.updateIdea(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ideas'] }),
  })

  if (isLoading) return (
    <div className="flex items-center justify-center h-64 text-[#6b7280]">
      Fetching Substack feeds… (first load ~15 s)
    </div>
  )

  const substack: any[] = data?.substack || []
  const ideas: any[]    = data?.ideas    || []

  const bySource: Record<string, any[]> = {}
  for (const it of substack) {
    ;(bySource[it.source_name] = bySource[it.source_name] || []).push(it)
  }

  return (
    <div className="p-4">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        {[
          { label: 'Substack Articles', value: substack.length },
          { label: 'High Relevance', value: substack.filter(i => i.relevance >= 0.6).length },
          { label: 'Saved Ideas', value: ideas.length },
          { label: 'In Writing', value: ideas.filter(i => i.status === 'writing').length },
        ].map(s => (
          <div key={s.label} className="bg-[#0f1117] border border-[#1e2130] rounded p-3 text-center">
            <div className="text-xl font-bold text-white">{s.value}</div>
            <div className="text-[11px] text-[#6b7280] mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Filter + Refresh */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-1">
          {(['all', 'substack', 'ideas'] as SourceFilter[]).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`text-xs px-3 py-1.5 rounded capitalize transition-colors ${
                filter === f
                  ? 'bg-[#2d3148] text-white'
                  : 'bg-[#0f1117] text-[#6b7280] hover:text-white'
              }`}>
              {f === 'all' ? '📚 All' : f === 'substack' ? '📰 Substack' : '💡 Saved Ideas'}
            </button>
          ))}
        </div>
        <button onClick={() => { qc.invalidateQueries({ queryKey: ['ideas'] }); refetch() }}
          className="text-xs px-3 py-1.5 bg-[#1e2130] hover:bg-[#2d3148] text-[#9ca3af] rounded transition-colors">
          ↻ Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* LEFT: Substack */}
        {filter !== 'ideas' && (
          <div>
            <h3 className="text-sm font-semibold text-[#9ca3af] mb-3 uppercase tracking-wider">
              📰 Substack ({substack.length})
            </h3>
            {Object.entries(bySource)
              .sort(([, a], [, b]) => Math.max(...b.map(i => i.relevance)) - Math.max(...a.map(i => i.relevance)))
              .map(([source, items]) => (
                <div key={source} className="mb-3">
                  <p className="text-[11px] font-semibold text-[#60a5fa] mb-1 px-1">{source}</p>
                  {items.map(it => (
                    <SubstackCard key={it.id} item={it} onSave={(item) => saveMut.mutate(item)} />
                  ))}
                </div>
              ))
            }
            {substack.length === 0 && (
              <p className="text-[#4b5563] text-sm">
                No articles cached yet. Click Refresh to fetch all 12 Substack feeds.
              </p>
            )}
          </div>
        )}

        {/* RIGHT: Ideas queue */}
        {filter !== 'substack' && (
          <div className={filter === 'ideas' ? 'col-span-2' : ''}>
            <h3 className="text-sm font-semibold text-[#9ca3af] mb-3 uppercase tracking-wider">
              💡 Article Ideas Queue ({ideas.length})
            </h3>
            {ideas.map(it => (
              <IdeasCard key={it.id} item={it}
                onStatus={(id, status) => statusMut.mutate({ id, status })} />
            ))}
            {ideas.length === 0 && (
              <div className="bg-[#0f1117] border border-dashed border-[#1e2130] rounded p-6 text-center">
                <p className="text-[#4b5563] text-sm">No saved ideas yet.</p>
                <p className="text-[#374151] text-xs mt-1">
                  Click "+ Save Idea" on any Substack article to add it here.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
