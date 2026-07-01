import { useEffect, useRef, useState } from 'react'

type Msg = { role: 'user' | 'assistant'; content: string }
type TraceItem = { step: number; name: string }

const API = ''  // 同源经 Vite 代理

export default function App() {
  const [sid, setSid] = useState<string>('')
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [trace, setTrace] = useState<TraceItem[]>([])
  const [todos, setTodos] = useState<{ content: string; status: string }[]>([])
  const [assets, setAssets] = useState<{ kind: string; path: string }[]>([])
  const [kbUsed, setKbUsed] = useState<string[]>([])
  const [loadedSkills, setLoadedSkills] = useState<string[]>([])
  const logRef = useRef<HTMLDivElement>(null)

  // 创建会话
  async function newSession() {
    const r = await fetch(`${API}/api/sessions`, { method: 'POST' })
    const d = await r.json()
    setSid(d.session_id)
    setMessages([])
    setTrace([])
    setTodos([])
    setAssets([])
    setKbUsed([])
    setLoadedSkills([])
  }

  useEffect(() => { newSession() }, [])

  // 上传文件（数据或文档）
  async function upload(file: File, kb?: string) {
    if (!sid) return
    const fd = new FormData()
    fd.append('file', file)
    const url = `${API}/api/sessions/${sid}/upload${kb ? `?kb=${encodeURIComponent(kb)}` : ''}`
    const r = await fetch(url, { method: 'POST', body: fd })
    const d = await r.json()
    if (d.kind === 'dataset') {
      setMessages(m => [...m, { role: 'user', content: `[上传数据] ${d.name}（${d.rows}行×${d.cols}列）` }])
    } else {
      setMessages(m => [...m, { role: 'user', content: `[上传文档到知识库 ${d.kb}] ${d.chunks}片段/${d.chars}字符` }])
    }
  }

  // 发送消息（SSE 流式）
  async function send() {
    if (!input.trim() || !sid || streaming) return
    const text = input
    setInput('')
    setStreaming(true)
    setMessages(m => [...m, { role: 'user', content: text }, { role: 'assistant', content: '' }])
    const idx = messages.length + 1

    const resp = await fetch(`${API}/api/sessions/${sid}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    })
    const reader = resp.body!.getReader()
    const dec = new TextDecoder()
    let buf = ''
    let assistantText = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        const data = line.replace(/^data: /, '').trim()
        if (!data) continue
        try {
          const ev = JSON.parse(data)
          if (ev.type === 'text') assistantText += ev.delta
          else if (ev.type === 'tool_call') assistantText += `\n[🔧 调用工具 ${ev.data.name}]`
          else if (ev.type === 'tool_result') assistantText += `\n[✓ ${ev.data.name} 完成]`
          else if (ev.type === 'done') { assistantText += ev.result ? '' : '' }
          else if (ev.type === 'error') assistantText += `\n[错误] ${ev.data.message}`
          setMessages(m => {
            const cp = [...m]
            cp[idx] = { role: 'assistant', content: assistantText }
            return cp
          })
        } catch {}
      }
    }
    setStreaming(false)
    refreshMeta()
  }

  async function refreshMeta() {
    if (!sid) return
    const r = await fetch(`${API}/api/sessions/${sid}/trace`)
    const d = await r.json()
    setTrace(d.trace || [])
    setTodos(d.todos || [])
    setAssets([d.report_path, d.report_pdf_path, d.ppt_path]
      .filter(Boolean).map(p => ({ kind: p.endsWith('.pptx') ? 'PPT' : p.endsWith('.pdf') ? 'PDF' : 'HTML', path: p })))
    setKbUsed(d.kb_used || [])
    setLoadedSkills(d.loaded_skills || [])
  }

  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight) }, [messages])

  return (
    <div className="flex h-screen bg-gray-50 text-gray-800">
      {/* 左：对话区 */}
      <div className="flex flex-col flex-1 max-w-3xl mx-auto w-full border-x border-gray-200 bg-white">
        <header className="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-red-600">办公小浣熊 Raccoon</h1>
            <p className="text-xs text-gray-400">AI 数据分析助手 · 会话 {sid || '…'}</p>
          </div>
          <button onClick={newSession} className="text-xs px-3 py-1.5 rounded bg-gray-100 hover:bg-gray-200">新建会话</button>
        </header>

        {/* 消息流 */}
        <div ref={logRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-400 mt-20">
              <p className="text-sm">上传数据或文档，然后提问。</p>
              <p className="text-xs mt-2">示例：「分析各区域销售趋势与异常」<br/>或「基于 @公司介绍 写一封商务合作邮件」</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] px-4 py-2.5 rounded-2xl whitespace-pre-wrap text-sm leading-relaxed ${
                m.role === 'user' ? 'bg-red-500 text-white' : 'bg-gray-100 text-gray-800'
              }`}>{m.content || (streaming ? '思考中…' : '')}</div>
            </div>
          ))}
        </div>

        {/* 上传 + 输入 */}
        <div className="border-t border-gray-200 px-3 py-2">
          <div className="flex gap-2 mb-2">
            <label className="text-xs px-2.5 py-1 rounded bg-blue-50 text-blue-600 cursor-pointer hover:bg-blue-100">
              📊 上传数据
              <input type="file" className="hidden" accept=".csv,.xlsx,.xls" onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
            <label className="text-xs px-2.5 py-1 rounded bg-green-50 text-green-600 cursor-pointer hover:bg-green-100">
              📄 上传文档(@知识库)
              <input type="file" className="hidden" accept=".txt,.md,.pdf,.docx"
                onChange={e => { const f = e.target.files?.[0]; if (f) { const kb = prompt('知识库名', 'default'); upload(f, kb || 'default') } }} />
            </label>
          </div>
          <div className="flex gap-2">
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && send()}
              placeholder="提问…（支持 @知识库名 / @writing）"
              className="flex-1 px-3.5 py-2 rounded-full border border-gray-300 text-sm focus:outline-none focus:border-red-400" />
            <button onClick={send} disabled={streaming || !input.trim()}
              className="px-4 py-2 rounded-full bg-red-500 text-white text-sm disabled:opacity-40 hover:bg-red-600">
              {streaming ? '…' : '发送'}
            </button>
          </div>
        </div>
      </div>

      {/* 右：状态面板 */}
      <aside className="w-72 border-l border-gray-200 bg-white overflow-y-auto p-4 space-y-4 hidden lg:block">
        <Section title="任务清单">
          {todos.length === 0 ? <Empty /> : todos.map((t, i) => (
            <div key={i} className="text-xs flex gap-1.5 py-0.5">
              <span>{t.status === 'done' ? '✓' : '○'}</span><span>{t.content}</span>
            </div>
          ))}
        </Section>
        <Section title="工具调用追溯">
          {trace.length === 0 ? <Empty /> : trace.map((t, i) => (
            <div key={i} className="text-xs text-gray-500">步骤{t.step} → <span className="text-gray-800">{t.name}</span></div>
          ))}
        </Section>
        <Section title="知识库 / Skills">
          {kbUsed.length === 0 && loadedSkills.length === 0 ? <Empty /> : (
            <div className="text-xs space-y-1">
              {kbUsed.map(k => <div key={k} className="text-green-600">📚 {k}</div>)}
              {loadedSkills.map(s => <div key={s} className="text-purple-600">⚙️ {s}</div>)}
            </div>
          )}
        </Section>
        <Section title="交付产物">
          {assets.length === 0 ? <Empty /> : assets.map((a, i) => (
            <a key={i} href={`${API}/api/files/${a.path}`} target="_blank"
               className="block text-xs text-blue-600 hover:underline py-0.5">📥 下载 {a.kind} 报告</a>
          ))}
        </Section>
      </aside>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1.5">{title}</h3>
      <div>{children}</div>
    </div>
  )
}
function Empty() { return <div className="text-xs text-gray-300">—</div> }
