import axios from 'axios'

const ax = axios.create({ baseURL: '' })

export const api = {
  fearGreed:   () => ax.get('/api/fear-greed').then(r => r.data),
  macro:       () => ax.get('/api/macro').then(r => r.data),
  sectors:     () => ax.get('/api/sectors').then(r => r.data),
  screener:    () => ax.get('/api/screener').then(r => r.data),
  stock:       (ticker: string, period = '6mo') => ax.get(`/api/stock/${ticker}`, { params: { period } }).then(r => r.data),
  institutional: (ticker: string) => ax.get(`/api/institutional/${ticker}`).then(r => r.data),
  earnings:    () => ax.get('/api/earnings').then(r => r.data),
  pipeline:    () => ax.get('/api/pipeline').then(r => r.data),
  feed:        () => ax.get('/api/feed').then(r => r.data),
  ideas:       () => ax.get('/api/ideas').then(r => r.data),
  saveIdea:    (body: object) => ax.post('/api/ideas/save', body).then(r => r.data),
  updateIdea:  (id: string, status: string) => ax.post(`/api/ideas/${id}/status`, { status }).then(r => r.data),
}

export async function* streamChat(messages: any[], snapshot: string) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, snapshot }),
  })
  const reader = res.body!.getReader()
  const dec = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data:')) {
        const raw = line.slice(5).trim()
        if (!raw) continue
        try { yield JSON.parse(raw) } catch { }
      }
      if (line.startsWith('event:')) {
        // event type embedded in next data line — handled via data payload
      }
    }
  }
}
