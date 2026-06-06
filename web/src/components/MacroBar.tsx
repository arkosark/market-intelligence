import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

export default function MacroBar() {
  const { data = [] } = useQuery({ queryKey: ['macro'], queryFn: api.macro, refetchInterval: 60000 })
  return (
    <div className="flex gap-4 px-4 py-2 bg-[#0f1117] border-b border-[#1e2130] overflow-x-auto text-xs">
      {data.map((m: any) => (
        <div key={m.name} className="flex items-center gap-1.5 whitespace-nowrap">
          <span className="text-[#64748b]">{m.name}</span>
          <span className="font-mono font-semibold">{m.value}</span>
          <span className={m.change >= 0 ? 'metric-up' : 'metric-down'}>
            {m.change >= 0 ? '+' : ''}{m.change}%
          </span>
        </div>
      ))}
    </div>
  )
}
