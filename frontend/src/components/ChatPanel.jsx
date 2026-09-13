import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api'

export default function ChatPanel({ projectId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const listRef = useRef(null)

  useEffect(() => {
    api.chatHistory(projectId)
      .then((data) => {
        const msgs = data
          .slice()
          .reverse()
          .map((m) => ({ role: m.role, content: m.content, sources: m.sources }))
        setMessages(msgs)
      })
      .catch(() => {})
  }, [projectId])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: text }])
    setSending(true)
    try {
      const res = await api.chat(projectId, text)
      setMessages((m) => [...m, { role: 'assistant', content: res.answer, sources: res.sources?.join('；') }])
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `出错了：${e.message}` }])
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="board-panel full">
      <div className="panel-head">
        <span>💬 项目智能助手</span>
        <span className="badge">基于项目事实 · 有据可查</span>
      </div>
      <div className="chat-panel">
        <div className="chat-messages" ref={listRef}>
          {messages.length === 0 && (
            <div className="empty">
              向助手提问，例如「本项目的合同金额是多少？」「有哪些干系人？」<br />
              回答将基于已识别的项目事实，标注来源，可追溯。
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.role === 'assistant' ? (
                <div className="md-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                </div>
              ) : (
                <span className="msg-plain">{m.content}</span>
              )}
              {m.role === 'assistant' && m.sources && (
                <div className="sources">来源：{m.sources}</div>
              )}
            </div>
          ))}
          {sending && (
            <div className="msg assistant"><span className="spinner" /> 正在思考并核对事实…</div>
          )}
        </div>
        <div className="chat-input">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
            }}
            placeholder="输入问题，Enter 发送，Shift+Enter 换行"
          />
          <button className="btn primary" onClick={send} disabled={sending || !input.trim()}>发送</button>
        </div>
      </div>
    </div>
  )
}
