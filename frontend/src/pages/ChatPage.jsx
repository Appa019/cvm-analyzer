import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { apiFetch, parseApiError } from '../utils/api'
import {
  PaperPlaneRight, PlusCircle, ChatsTeardrop, BookOpenText,
  ArrowSquareOut, TrashSimple, Lightning, CheckCircle, Warning
} from '@phosphor-icons/react'
import useCompanyStore from '../store/companyStore'

export default function ChatPage() {
  const { authHeaders } = useAuth()
  const { selectedCompany } = useCompanyStore()
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [sessionsError, setSessionsError] = useState('')

  // Indexação inteligente
  const [companyStatus, setCompanyStatus] = useState(null) // {has_vs, indexed_count, new_count}
  const [indexing, setIndexing] = useState(false)
  const [indexProgress, setIndexProgress] = useState(null) // {done, total, file}
  const [indexMsg, setIndexMsg] = useState(null)

  const messagesEndRef = useRef(null)

  useEffect(() => { loadSessions() }, [])
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, typing])

  useEffect(() => {
    setCompanyStatus(null)
    setIndexMsg(null)
    const cnpj = selectedCompany?.cnpj
    if (!cnpj || typeof cnpj !== 'string' || !cnpj.trim()) return
    checkCompanyStatus()
  }, [selectedCompany])

  async function checkCompanyStatus() {
    const cnpj = selectedCompany?.cnpj
    if (!cnpj) return
    try {
      const res = await fetch(
        `/api/chat/company-status?cnpj=${encodeURIComponent(cnpj)}`,
        { headers: authHeaders() }
      )
      if (res.ok) setCompanyStatus(await res.json())
    } catch (err) {
      console.error('[ChatPage] Erro ao verificar status:', err.message)
    }
  }

  async function handleIndex(newOnly = true) {
    if (!selectedCompany?.cnpj || indexing) return
    setIndexing(true)
    setIndexProgress({ done: 0, total: 0, file: '' })
    setIndexMsg(null)
    try {
      const res = await fetch('/api/chat/index-company', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cnpj_cia: selectedCompany.cnpj,
          company_name: selectedCompany.name || '',
          new_only: newOnly,
        }),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          try {
            const evt = JSON.parse(line.slice(5).trim())
            if (evt.status === 'start') setIndexProgress({ done: 0, total: evt.total, file: '' })
            else if (evt.status === 'done') {
              setIndexMsg({ type: 'ok', text: `Indexação concluída: ${evt.indexed} arquivo(s) indexado(s).` })
              setIndexProgress(null)
              checkCompanyStatus()
            } else if (evt.status === 'error') {
              setIndexMsg({ type: 'error', text: evt.detail || 'Erro na indexação.' })
              setIndexProgress(null)
            } else if (evt.done !== undefined) {
              setIndexProgress({ done: evt.done, total: evt.total, file: evt.file || '' })
            }
          } catch {}
        }
      }
    } catch (err) {
      setIndexMsg({ type: 'error', text: 'Erro ao indexar: ' + err.message })
      setIndexProgress(null)
    } finally {
      setIndexing(false)
    }
  }

  async function loadSessions() {
    try {
      const res = await apiFetch('/api/chat/sessions', { headers: authHeaders() })
      const data = await res.json()
      setSessions(data.sessions || [])
      setSessionsError('')
    } catch (err) {
      console.error('[ChatPage] Erro ao carregar sessões:', err.message)
      setSessionsError(parseApiError(err))
    }
  }

  async function createSession() {
    try {
      const body = {}
      if (selectedCompany?.cnpj) {
        body.cnpj_cia = selectedCompany.cnpj
        body.company_name = selectedCompany.name || ''
      }
      const res = await apiFetch('/api/chat/sessions', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      setSessions(prev => [{ ...data, message_count: 0 }, ...prev])
      setActiveSessionId(data.session_id)
      setMessages([])
      setSessionsError('')
    } catch (err) {
      console.error('[ChatPage] Erro ao criar sessão:', err.message)
      setSessionsError(parseApiError(err))
    }
  }

  async function loadHistory(sessionId) {
    try {
      const res = await apiFetch(`/api/chat/sessions/${sessionId}`, { headers: authHeaders() })
      const data = await res.json()
      setMessages(data.messages || [])
    } catch (err) {
      console.error('[ChatPage] Erro ao carregar histórico da sessão:', err.message)
    }
  }

  async function deleteSession(e, sessionId) {
    e.stopPropagation()
    try {
      await apiFetch(`/api/chat/sessions/${sessionId}`, { method: 'DELETE', headers: authHeaders() })
      setSessions(prev => prev.filter(s => s.session_id !== sessionId))
      if (activeSessionId === sessionId) { setActiveSessionId(null); setMessages([]) }
    } catch (err) {
      console.error('[ChatPage] Erro ao deletar sessão:', err.message)
    }
  }

  async function handleSend(e) {
    e.preventDefault()
    if (!input.trim() || !activeSessionId || typing) return
    const msg = input.trim()
    setMessages(prev => [...prev, { role: 'user', content: msg, sources: [], web_sources: [], created_at: new Date().toISOString() }])
    setInput('')
    setTyping(true)
    try {
      const res = await apiFetch(`/api/chat/sessions/${activeSessionId}/messages`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, data])
      setSessions(prev => prev.map(s => s.session_id === activeSessionId ? { ...s, message_count: (s.message_count || 0) + 2 } : s))
    } catch (err) {
      const errMsg = parseApiError(err, 'Não foi possível obter resposta.')
      setMessages(prev => [...prev, { role: 'assistant', content: `Erro: ${errMsg}`, sources: [], web_sources: [], created_at: new Date().toISOString() }])
    } finally { setTyping(false) }
  }

  function selectSession(sessionId) {
    setActiveSessionId(sessionId)
    loadHistory(sessionId)
  }

  // Painel de status de indexação
  function IndexPanel() {
    if (!selectedCompany) return null
    const hasNew = companyStatus && companyStatus.new_count > 0
    const isIndexed = companyStatus?.has_vs
    return (
      <div className="index-panel">
        {companyStatus ? (
          <div className="index-status">
            {isIndexed
              ? <CheckCircle size={14} weight="duotone" style={{ color: '#22c55e' }} />
              : <Warning size={14} weight="duotone" style={{ color: '#f59e0b' }} />}
            <span>
              {isIndexed
                ? `${companyStatus.indexed_count} doc(s) indexado(s)`
                : 'Nenhum documento indexado'}
              {hasNew && <span style={{ color: '#f59e0b' }}> · {companyStatus.new_count} novo(s)</span>}
            </span>
            {(hasNew || !isIndexed) && (
              <button
                className="btn btn-xs"
                style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4 }}
                onClick={() => handleIndex(true)}
                disabled={indexing}
              >
                <Lightning size={12} weight="duotone" />
                {indexing ? 'Indexando...' : 'Indexar novos'}
              </button>
            )}
            {isIndexed && !hasNew && (
              <button
                className="btn btn-xs"
                style={{ marginLeft: 'auto', fontSize: '0.7rem', opacity: 0.6 }}
                onClick={() => handleIndex(false)}
                disabled={indexing}
              >
                Re-indexar tudo
              </button>
            )}
          </div>
        ) : (
          <div className="index-status" style={{ color: '#9ca3af', fontSize: '0.75rem' }}>
            Verificando indexação...
          </div>
        )}

        {indexing && indexProgress && (
          <div style={{ marginTop: '6px' }}>
            <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: '3px' }}>
              {indexProgress.file ? `Indexando: ${indexProgress.file}` : 'Iniciando...'}
              {indexProgress.total > 0 && ` (${indexProgress.done}/${indexProgress.total})`}
            </div>
            {indexProgress.total > 0 && (
              <div style={{ background: 'var(--border)', borderRadius: 4, height: 4 }}>
                <div style={{
                  background: 'var(--primary)',
                  borderRadius: 4,
                  height: 4,
                  width: `${Math.round((indexProgress.done / indexProgress.total) * 100)}%`,
                  transition: 'width 0.3s'
                }} />
              </div>
            )}
          </div>
        )}

        {indexMsg && (
          <div style={{ marginTop: '4px', fontSize: '0.75rem', color: indexMsg.type === 'ok' ? '#22c55e' : '#ef4444' }}>
            {indexMsg.text}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="chat-layout">
      <aside className="chat-sidebar">
        <div className="chat-sidebar-header">
          <span className="chat-sidebar-title">Conversas</span>
          <button className="btn-icon" onClick={createSession} title="Nova conversa">
            <PlusCircle size={20} weight="duotone" />
          </button>
        </div>

        <IndexPanel />

        {sessionsError && <div className="alert alert-error" style={{ margin: '8px', fontSize: 12 }}>{sessionsError}</div>}
        {!sessionsError && sessions.length === 0 && <div className="empty-hint">Clique + para iniciar</div>}
        {sessions.map(s => (
          <div key={s.session_id} className={`session-item${activeSessionId === s.session_id ? ' active' : ''}`}>
            <button className="session-btn" onClick={() => selectSession(s.session_id)}>
              <ChatsTeardrop size={16} weight="duotone" />
              <div className="session-info">
                <div className="session-title">{s.company_name || s.document_id || 'Conversa Geral'}</div>
                <div className="session-meta">{s.message_count || 0} msgs</div>
              </div>
            </button>
            <button className="btn-icon btn-icon-sm danger" onClick={e => deleteSession(e, s.session_id)}>
              <TrashSimple size={14} weight="duotone" />
            </button>
          </div>
        ))}
      </aside>

      <div className="chat-main">
        {!activeSessionId ? (
          <div className="chat-empty">
            <ChatsTeardrop size={52} weight="duotone" className="chat-empty-icon" />
            <h3>Bem-vindo ao Chat IA</h3>
            <p>
              {selectedCompany
                ? <>Empresa: <strong>{selectedCompany.name}</strong>.<br /></>
                : <>Selecione uma empresa na barra lateral e indexe os documentos antes de iniciar.<br /></>}
              As respostas são fundamentadas nos documentos baixados (FRE, DFP, FCA, IPE).
            </p>
            <button className="btn btn-primary" onClick={createSession}>Iniciar Conversa</button>
          </div>
        ) : (
          <>
            <div className="chat-messages">
              {messages.map((msg, idx) => (
                <div key={idx} className={`message message-${msg.role}`}>
                  <div className="message-bubble">
                    <div className="message-content">{msg.content}</div>
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="message-sources">
                        {msg.sources.map((src, si) => (
                          <div key={si} className="source-citation">
                            <BookOpenText size={13} weight="duotone" />
                            <span>{src.item_id} — {src.tipo_doc || 'DOC'} {src.dt_refer?.slice(0, 4)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {msg.web_sources && msg.web_sources.length > 0 && (
                      <div className="message-sources">
                        {msg.web_sources.map((src, si) => (
                          <div key={si} className="source-citation">
                            <ArrowSquareOut size={13} weight="duotone" />
                            <a href={src.url} target="_blank" rel="noopener noreferrer">
                              {src.title || src.url}
                            </a>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {typing && (
                <div className="message message-assistant">
                  <div className="message-bubble typing-bubble">
                    <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <form className="chat-input-form" onSubmit={handleSend}>
              <input
                className="chat-input"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Faça uma pergunta sobre os documentos..."
                disabled={typing}
                autoFocus
              />
              <button type="submit" className="btn btn-primary" disabled={!input.trim() || typing}>
                <PaperPlaneRight size={18} weight="duotone" />
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
