import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './App.css'

const API_BASE = '/api'

function EvidenceBadge({ level, levelName }) {
  const levelConfig = {
    4: { color: 'var(--evidence-high)', label: '高' },
    3: { color: 'var(--evidence-medium)', label: '中' },
    2: { color: 'var(--evidence-low)', label: '低' },
    1: { color: 'var(--evidence-very-low)', label: '参考' },
  }
  const cfg = levelConfig[level] || levelConfig[1]
  return (
    <span
      className="evidence-badge"
      style={{ backgroundColor: cfg.color, color: 'var(--bg-primary)' }}
      title={`证据等级 Level ${level}: ${levelName}`}
    >
      Level {level} · {cfg.label}
    </span>
  )
}

function EvidenceCard({ evidence, index }) {
  const [showExplanation, setShowExplanation] = useState(false)
  return (
    <div className="evidence-card">
      <div className="evidence-header">
        <EvidenceBadge level={evidence.evidence_level} levelName={evidence.evidence_level_name} />
        <span className="evidence-source">
          {evidence.source_name}
          {evidence.publication_date && ` · ${evidence.publication_date}`}
        </span>
        <button
          className="explain-btn"
          onClick={() => setShowExplanation(!showExplanation)}
          title="查看分级说明"
        >
          ?
        </button>
      </div>
      {showExplanation && evidence.level_explanation && (
        <div className="evidence-explanation">{evidence.level_explanation}</div>
      )}
      <p className="evidence-content">{evidence.content}</p>
      {evidence.source_url && (
        <a href={evidence.source_url} target="_blank" rel="noopener noreferrer" className="evidence-link">
          查看来源 →
        </a>
      )}
    </div>
  )
}

function ChatMessageBubble({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`bubble ${isUser ? 'user' : 'assistant'}`}>
      <div className="bubble-content">
        {isUser ? (
          msg.content
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} className="markdown-body">
            {msg.content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  )
}

function Disclaimer() {
  return (
    <div className="disclaimer">
      <strong>免责声明：</strong>
      本系统为课程设计原型，其提供的信息仅供学术研究和参考，不能作为专业的医疗诊断和治疗建议。如有任何健康问题，请务必咨询执业医师。
    </div>
  )
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [lastWasClarification, setLastWasClarification] = useState(false)
  const [evidences, setEvidences] = useState([])
  const [disclaimer, setDisclaimer] = useState('')
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setLoading(true)
    setEvidences([])

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId || '',
          message: text,
          conversation_history: messages,
          is_clarification_response: lastWasClarification,
        }),
      })
      const data = await res.json()

      if (!res.ok) throw new Error(data.detail || '请求失败')

      if (data.session_id && !sessionId) setSessionId(data.session_id)

      if (data.needs_clarification && data.clarification_question) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: data.clarification_question },
        ])
        setLastWasClarification(true)
      } else {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: data.answer },
        ])
        setEvidences(data.evidences || [])
        setDisclaimer(data.disclaimer || '')
        setLastWasClarification(false)
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `错误：${err.message}` },
      ])
      setLastWasClarification(false)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>在线健康问答助手</h1>
        <p>基于证据分级与多轮澄清</p>
        <p className="disclaimer-header">免责声明：本系统仅供学术研究参考，不能替代专业医疗建议，请咨询执业医师。</p>
      </header>

      <main className="chat-area">
        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <p>您好！我是健康问答助手，可以为您解答常见健康问题。</p>
              <p>示例：高血压患者的饮食建议、发烧怎么办、头痛如何缓解</p>
              <p className="hint">提示：若问题较模糊，我会先向您追问以提供更精准的建议。</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <ChatMessageBubble key={i} msg={msg} />
          ))}
          {loading && (
            <div className="bubble assistant loading">
              <span className="dot">.</span>
              <span className="dot">.</span>
              <span className="dot">.</span>
            </div>
          )}
          <div ref={scrollRef} />
        </div>

        {evidences.length > 0 && (
          <div className="evidences-panel">
            <h3>参考资料与证据等级</h3>
            {evidences.map((e, i) => (
              <EvidenceCard key={i} evidence={e} index={i} />
            ))}
          </div>
        )}

        {(disclaimer || evidences.length > 0) && <Disclaimer />}
      </main>

      <footer className="input-area">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
          placeholder="输入您的健康问题..."
          disabled={loading}
        />
        <button onClick={sendMessage} disabled={loading}>
          发送
        </button>
      </footer>
    </div>
  )
}
