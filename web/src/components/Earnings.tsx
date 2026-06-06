import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

export default function Earnings() {
  const { data = [], isLoading } = useQuery({ queryKey: ['earnings'], queryFn: api.earnings, staleTime: 3600000 })

  return (
    <div className="flex flex-col gap-4 p-4 overflow-auto">
      <div className="card">
        <div className="text-xs text-[#64748b] uppercase tracking-widest mb-3">Upcoming Earnings Calendar</div>
        {isLoading ? (
          <div className="text-[#64748b] text-sm py-8 text-center">Loading…</div>
        ) : (
          <>
            <table className="w-full text-xs mb-6">
              <thead>
                <tr className="text-[#64748b] border-b border-[#1e2130]">
                  {['Ticker','Date','Days Away','EPS Est','Rev Est ($B)'].map(h => (
                    <th key={h} className="text-left py-2 px-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((r: any) => (
                  <tr key={r.ticker} className="border-b border-[#0a0a0f] hover:bg-[#1a1a2e] transition-colors">
                    <td className="py-1.5 px-2 font-bold text-[#3b82f6]">{r.ticker}</td>
                    <td className="py-1.5 px-2 font-mono">{r.date}</td>
                    <td className="py-1.5 px-2">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium
                        ${r.daysAway <= 7 ? 'bg-red-900/40 text-red-400' :
                          r.daysAway <= 21 ? 'bg-yellow-900/40 text-yellow-400' :
                          'bg-green-900/40 text-green-400'}`}>
                        {r.daysAway}d
                      </span>
                    </td>
                    <td className="py-1.5 px-2 font-mono">{r.epsEst ?? '—'}</td>
                    <td className="py-1.5 px-2 font-mono">{r.revEst ? `$${r.revEst}B` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Timeline */}
            <div className="text-xs text-[#64748b] uppercase tracking-widest mb-3">Timeline</div>
            <div className="relative">
              <div className="absolute top-3 left-0 right-0 h-px bg-[#1e2130]"/>
              <div className="flex flex-wrap gap-x-6 gap-y-8 py-6">
                {data.map((r: any) => (
                  <div key={r.ticker} className="flex flex-col items-center gap-1 relative">
                    <div className={`w-3 h-3 rounded-full border-2
                      ${r.daysAway <= 7 ? 'bg-red-500 border-red-400' :
                        r.daysAway <= 21 ? 'bg-yellow-500 border-yellow-400' :
                        'bg-green-500 border-green-400'}`}/>
                    <span className="font-bold text-[#3b82f6] text-xs">{r.ticker}</span>
                    <span className="text-[#64748b] text-[10px]">{r.date}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
