import { useState, useRef, useEffect } from 'react'
import { streamChat } from '../api'

interface Msg { role: 'user' | 'assistant'; content: string }
interface ToolCall { tool: string; input: any }

export default function ChatPanel({ snapshot }: { snapshot: string }) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [tools, setTools] = useState<ToolCall[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, tools])

  async function send(text?: string) {
    const msg = (text ?? input).trim()
    if (!msg || streaming) return
    setInput('')
    const userMsg: Msg = { role: 'user', content: msg }
    setMessages(prev => [...prev, userMsg])
    setTools([])
    setStreaming(true)

    const apiMsgs = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }))
    let assistantText = ''
    const idx = messages.length + 1

    setMessages(prev => [...prev, { role: 'assistant', content: '' }])

    try {
      for await (const chunk of streamChat(apiMsgs, snapshot)) {
        if (chunk.tool) {
          setTools(prev => [...prev, chunk])
        } else if (chunk.text) {
          assistantText += chunk.text
          setMessages(prev => {
            const updated = [...prev]
            updated[idx] = { role: 'assistant', content: assistantText }
            return updated
          })
        }
      }
    } catch (e) {
      console.error(e)
    } finally {
      setStreaming(false)
    }
  }

  function clear() { setMessages([]); setTools([]) }

  const width = expanded ? 'w-[480px]' : 'w-64'

  return (
    <div className={`${width} flex-shrink-0 flex flex-col border-l border-[#1e2130] bg-[#0a0a0f] transition-all duration-200`}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#1e2130]">
        <span className="text-xs font-semibold text-[#94a3b8] uppercase tracking-widest">🤖 AI Analyst</span>
        <div className="flex gap-1">
          {messages.length > 0 && (
            <button onClick={clear} className="text-[10px] text-[#64748b] hover:text-[#94a3b8] px-2 py-0.5 rounded hover:bg-[#1e2130]">
              Clear
            </button>
          )}
          <button onClick={() => setExpanded(e => !e)}
            className="text-[10px] text-[#64748b] hover:text-[#94a3b8] px-2 py-0.5 rounded hover:bg-[#1e2130]">
            {expanded ? '◀ Less' : 'More ▶'}
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
        {messages.length === 0 && (
          <div className="text-[#2d2d3d] text-xs text-center mt-8 leading-relaxed">
            Ask about any stock,<br/>sector, or signal.<br/><br/>
            <span className="text-[#1e2130]">e.g. "Is NVDA a good entry?"<br/>"Top healthcare stocks?"<br/>"What's the market sentiment?"</span>
          </div>
        )}
        {tools.map((t, i) => (
          <div key={`tool-${i}`} className="chat-tool">
            🔍 Fetching {t.input?.ticker ?? t.input?.sector ?? t.tool}…
          </div>
        ))}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'chat-user' : 'chat-assistant'}>
            <div className="text-[10px] font-semibold mb-1 text-[#64748b]">
              {m.role === 'user' ? 'You' : 'AI Analyst'}
            </div>
            <div className="text-xs leading-relaxed whitespace-pre-wrap">{m.content}
              {streaming && i === messages.length - 1 && m.role === 'assistant' && (
                <span className="inline-block w-1.5 h-3 bg-[#10b981] ml-0.5 animate-pulse"/>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef}/>
      </div>

      {/* Input */}
      <div className="p-2 border-t border-[#1e2130]">
        <div className="flex gap-1.5">
          <textarea ref={textRef} value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="Ask anything…"
            rows={2}
            className="flex-1 bg-[#0f1117] border border-[#1e2130] focus:border-[#3b82f6] rounded px-2 py-1.5 text-xs text-[#e2e8f0] placeholder-[#2d2d3d] resize-none outline-none"/>
          <button onClick={() => send()}
            disabled={streaming || !input.trim()}
            className="px-3 bg-[#3b82f6] hover:bg-[#2563eb] disabled:bg-[#1e2130] disabled:text-[#2d2d3d] text-white rounded text-xs font-medium transition-colors self-stretch">
            {streaming ? '…' : '↑'}
          </button>
        </div>
      </div>
    </div>
  )
}
