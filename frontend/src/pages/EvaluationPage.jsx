import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { apiFetch, parseApiError } from '../utils/api'
import { CloudArrowUp, CaretDown, CaretRight, CheckCircle, Warning, XCircle, Export, ClockCounterClockwise, FileArrowUp } from '@phosphor-icons/react'
import useCompanyStore from '../store/companyStore'

const STATUS_ICON = {
  COMPLETO: <CheckCircle size={16} weight="duotone" style={{ color: '#22c55e' }} />,
  PARCIAL: <Warning size={16} weight="duotone" style={{ color: '#f59e0b' }} />,
  AUSENTE: <XCircle size={16} weight="duotone" style={{ color: '#ef4444' }} />,
  CRITICO: <XCircle size={16} weight="duotone" style={{ color: '#dc2626' }} />,
}

const STATUS_CLASS = {
  COMPLETO: 'badge-success',
  PARCIAL: 'badge-warning',
  AUSENTE: 'badge-danger',
  CRITICO: 'badge-critical',
}

export default function EvaluationPage() {
  const { authHeaders } = useAuth()
  const { selectedCompany } = useCompanyStore()
  const [mode, setMode] = useState('local')
  const [activeTipo, setActiveTipo] = useState('Todos')
  const [localFiles, setLocalFiles] = useState([])
  const [selectedLocalFile, setSelectedLocalFile] = useState(null)
  const [uploadFile, setUploadFile] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [evalId, setEvalId] = useState(null)
  const [history, setHistory] = useState([])
  const [expanded, setExpanded] = useState(new Set())
  const [resolved, setResolved] = useState(new Set())
  const [historyLoading, setHistoryLoading] = useState(false)

  useEffect(() => { loadHistory() }, [])

  useEffect(() => {
    if (!selectedCompany?.cnpj) {
      setLocalFiles([]); setSelectedLocalFile(null)
      setActiveTipo('Todos')
      return
    }
    // Carrega arquivos locais (já baixados)
    fetch(`/api/archive/local-files?cnpj=${encodeURIComponent(selectedCompany.cnpj)}`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : { files: [] })
      .then(data => {
        const files = data.files || []
        setLocalFiles(files)
        setActiveTipo('Todos')
        setSelectedLocalFile(files[0] || null)
      })
      .catch(() => { setLocalFiles([]); setSelectedLocalFile(null) })
  }, [selectedCompany])

  async function loadHistory() {
    setHistoryLoading(true)
    try {
      const res = await apiFetch('/api/evaluation/history', { headers: authHeaders() })
      const data = await res.json()
      setHistory(data.evaluations || [])
    } catch (err) {
      console.error('[EvaluationPage] Erro ao carregar histórico:', err.message)
    } finally {
      setHistoryLoading(false)
    }
  }

  async function loadEvaluationById(id) {
    setError('')
    setLoading(true)
    setResult(null)
    try {
      const res = await apiFetch(`/api/evaluation/${id}`, { headers: authHeaders() })
      const data = await res.json()
      setResult(data)
      setEvalId(data.evaluation_id)
      setExpanded(new Set())
      setResolved(new Set())
      // Carregar issues resolvidas pelo usuário
      loadResolvedIssues(data.evaluation_id)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadResolvedIssues(id) {
    try {
      const res = await apiFetch(`/api/evaluation/${id}/issues/resolved`, { headers: authHeaders() })
      const data = await res.json()
      const keys = (data.resolved || []).map(r => `${r.item_id_str}_${r.issue_index}`)
      setResolved(new Set(keys))
    } catch (err) {
      console.error('[EvaluationPage] Erro ao carregar issues resolvidas:', err.message)
    }
  }

  async function handleEvaluate() {
    setError('')
    setLoading(true)
    setResult(null)
    setEvalId(null)
    try {
      let res
      if (mode === 'local') {
        if (!selectedLocalFile) { setError('Nenhum arquivo local disponível. Baixe documentos na aba Empresas.'); setLoading(false); return }
        res = await apiFetch('/api/evaluation/evaluate', {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            local_filename: selectedLocalFile.filename,
            cnpj: selectedCompany?.cnpj || '',
            dt_refer: selectedLocalFile.dt_refer || '',
            versao: selectedLocalFile.versao || 1,
          }),
        })
      } else {
        if (!uploadFile) { setError('Selecione um arquivo PDF'); setLoading(false); return }
        const fd = new FormData()
        fd.append('file', uploadFile)
        res = await apiFetch('/api/evaluation/upload', { method: 'POST', headers: authHeaders(), body: fd })
      }
      const data = await res.json()
      setResult(data)
      // API retorna `evaluation_id` (alinhado com FREEvaluation.id no DB)
      if (data.evaluation_id) {
        setEvalId(data.evaluation_id)
        loadResolvedIssues(data.evaluation_id)
      }
      loadHistory()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleResolve(itemIdStr, issueIndex) {
    if (!evalId) return
    const key = `${itemIdStr}_${issueIndex}`
    try {
      // API espera `item_id_str` (alinhado com IssueResolution.item_id_str no DB)
      const res = await apiFetch(`/api/evaluation/${evalId}/issues/resolve`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id_str: itemIdStr, issue_index: issueIndex }),
      })
      if (res.ok) setResolved(prev => new Set([...prev, key]))
    } catch (err) {
      console.error('[EvaluationPage] Erro ao resolver issue:', err.message)
    }
  }

  async function handleExport(fmt) {
    if (!evalId) return
    try {
      const res = await fetch(`/api/evaluation/${evalId}/export/${fmt}`, {
        headers: authHeaders(),
      })
      if (!res.ok) throw new Error('Erro ao exportar')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `avaliacao_${evalId}.${fmt}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('[EvaluationPage] Erro ao exportar:', err.message)
    }
  }

  function toggleItem(id) {
    setExpanded(prev => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  const TIPO_TABS = ['Todos', 'FRE', 'DFP', 'FCA', 'IPE']
  const filteredLocalFiles = activeTipo === 'Todos'
    ? localFiles
    : localFiles.filter(f => (f.tipo_doc || 'FRE').toUpperCase() === activeTipo)

  // total_score vem em escala 0–100 do banco de dados (FREEvaluation.total_score)
  const scorePercent = result ? Math.round(result.total_score || 0) : 0
  const scoreColor = scorePercent >= 80 ? '#48bb78' : scorePercent >= 50 ? '#ed8936' : '#e53e3e'

  function historyLabel(h) {
    if (h.is_uploaded && h.original_filename) return h.original_filename
    if (h.dt_refer) return `FRE ${h.dt_refer.slice(0, 4)} v${h.versao || 1}`
    return h.document_id || 'FRE'
  }

  function historyScore(h) {
    const pct = Math.round(h.total_score || 0)
    const color = pct >= 80 ? '#48bb78' : pct >= 50 ? '#ed8936' : '#e53e3e'
    return { pct, color }
  }

  return (
    <div className="page-layout">
      <aside className="page-sidebar">
        <div className="sidebar-section-title">Histórico</div>
        {historyLoading && <div className="empty-hint">Carregando...</div>}
        {!historyLoading && history.length === 0 && <div className="empty-hint">Nenhuma avaliação</div>}
        {history.map(h => {
          const { pct, color } = historyScore(h)
          const isActive = evalId === h.id
          return (
            <button
              key={h.id}
              className={`history-item${isActive ? ' active' : ''}`}
              onClick={() => loadEvaluationById(h.id)}
            >
              <div className="history-item-header">
                <div className="history-item-title" title={historyLabel(h)}>
                  {h.is_uploaded && <FileArrowUp size={13} weight="duotone" style={{ display: 'inline', marginRight: 4 }} />}
                  {historyLabel(h)}
                </div>
                <span className="history-item-score" style={{ color }}>{pct}%</span>
              </div>
              <div className="history-item-meta">
                <ClockCounterClockwise size={13} weight="duotone" />
                {h.evaluated_at
                  ? new Date(h.evaluated_at).toLocaleDateString('pt-BR')
                  : '—'}
                {(h.critical_count > 0 || h.absent_count > 0) && (
                  <span className="history-item-alerts">
                    {h.critical_count > 0 && <span className="badge badge-critical" style={{ fontSize: 10, padding: '0 4px' }}>{h.critical_count} C</span>}
                    {h.absent_count > 0 && <span className="badge badge-danger" style={{ fontSize: 10, padding: '0 4px' }}>{h.absent_count} A</span>}
                  </span>
                )}
              </div>
            </button>
          )
        })}
      </aside>

      <div className="page-main">
        <div className="page-header">
          <h1 className="page-title">Avaliação de Documentos</h1>
          <p className="page-subtitle">Análise de conformidade com a Resolução CVM 80 (FRE, DFP, FCA)</p>
        </div>

        <div className="card">
          <div className="mode-tabs">
            <button className={`mode-tab${mode === 'local' ? ' active' : ''}`} onClick={() => setMode('local')}>
              Arquivo Local
            </button>
            <button className={`mode-tab${mode === 'upload' ? ' active' : ''}`} onClick={() => setMode('upload')}>
              Upload PDF
            </button>
          </div>

          <div className="mode-content">
            {mode === 'local' ? (
              <div className="form-group">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <label className="form-label" style={{ margin: 0 }}>Arquivo já baixado</label>
                  <div className="filter-tabs" style={{ display: 'flex', gap: 4 }}>
                    {TIPO_TABS.map(t => (
                      <button
                        key={t}
                        className={`filter-tab${activeTipo === t ? ' active' : ''}`}
                        style={{ fontSize: '0.7rem', padding: '2px 7px' }}
                        onClick={() => {
                          setActiveTipo(t)
                          const next = t === 'Todos'
                            ? localFiles
                            : localFiles.filter(f => (f.tipo_doc || 'FRE').toUpperCase() === t)
                          setSelectedLocalFile(next[0] || null)
                        }}
                        type="button"
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
                {filteredLocalFiles.length === 0 ? (
                  <div className="empty-hint" style={{ padding: '0.75rem 0', color: '#9ca3af' }}>
                    {localFiles.length === 0
                      ? <>Nenhum arquivo local. Baixe documentos na aba <strong>Empresas</strong>.</>
                      : `Nenhum arquivo ${activeTipo} baixado.`}
                  </div>
                ) : (
                  <select className="form-select" value={selectedLocalFile?.filename || ''}
                    onChange={e => setSelectedLocalFile(filteredLocalFiles.find(f => f.filename === e.target.value))}>
                    {filteredLocalFiles.map(f => (
                      <option key={f.filename} value={f.filename}>
                        {f.tipo_doc || 'DOC'} {(f.dt_refer || '').slice(0, 4)} — {f.filename}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            ) : (
              <div
                className={`upload-zone${dragOver ? ' drag-over' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) setUploadFile(f) }}
                onClick={() => document.getElementById('pdf-upload').click()}
              >
                <CloudArrowUp size={36} weight="duotone" />
                <div>{uploadFile ? uploadFile.name : 'Arraste o PDF ou clique para selecionar'}</div>
                <input id="pdf-upload" type="file" accept=".pdf" style={{ display: 'none' }}
                  onChange={e => setUploadFile(e.target.files[0])} />
              </div>
            )}
          </div>

          {error && <div className="alert alert-error">{error}</div>}

          <button className="btn btn-primary" onClick={handleEvaluate} disabled={loading}>
            {loading ? 'Avaliando...' : 'Avaliar'}
          </button>
        </div>

        {loading && !result && (
          <div className="card" style={{ textAlign: 'center', color: '#718096', padding: '2rem' }}>
            Processando avaliação…
          </div>
        )}

        {result && (
          <div className="results-panel">
            <div className="results-header">
              <div className="score-ring" style={{ '--score-pct': scorePercent, '--score-color': scoreColor }}>
                <div className="score-ring-inner">
                  <span className="score-ring-value" style={{ color: scoreColor }}>{scorePercent}%</span>
                  <span className="score-ring-label">Score</span>
                </div>
              </div>
              <div className="results-meta">
                <div className="results-title">
                  {result.is_uploaded && result.document_id?.includes('upload_')
                    ? `Upload — ${result.dt_refer?.slice(0, 4) || ''}`
                    : result.document_id || 'FRE Avaliado'}
                </div>
                <div className="results-stats">
                  {/* Contagens alinhadas com FREEvaluation.{critical,absent,partial,complete}_count */}
                  {['CRITICO','AUSENTE','PARCIAL','COMPLETO'].map(s => {
                    const field = `${s.toLowerCase()}_count`
                    const count = result[field] ?? (result.items || []).filter(r => r.status === s).length
                    return count > 0 ? <span key={s} className={`badge ${STATUS_CLASS[s]}`}>{count} {s}</span> : null
                  })}
                </div>
                {evalId && (
                  <div className="export-btns">
                    <button className="btn btn-sm btn-secondary" onClick={() => handleExport('xlsx')}>
                      <Export size={14} weight="duotone" /> Excel
                    </button>
                    <button className="btn btn-sm btn-secondary" onClick={() => handleExport('pdf')}>
                      <Export size={14} weight="duotone" /> PDF
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div className="items-list">
              {/* API retorna `items` (alinhado com FREItemEvaluation) */}
              {(result.items || []).map(item => (
                <div key={item.item_id} className={`item-card item-${(item.status || '').toLowerCase()}`}>
                  <button className="item-header" onClick={() => toggleItem(item.item_id)}>
                    <div className="item-header-left">
                      {STATUS_ICON[item.status]}
                      <span className="item-id">{item.item_id}</span>
                      <span className="item-title">{item.titulo}</span>
                    </div>
                    <div className="item-header-right">
                      <span className={`badge ${STATUS_CLASS[item.status]}`}>{item.status}</span>
                      {expanded.has(item.item_id) ? <CaretDown size={16} weight="bold" /> : <CaretRight size={16} weight="bold" />}
                    </div>
                  </button>

                  {expanded.has(item.item_id) && (
                    <div className="item-detail">
                      {item.reasoning && (
                        <div className="item-section">
                          <div className="item-section-label">Análise</div>
                          <div className="item-section-content">{item.reasoning}</div>
                        </div>
                      )}
                      {item.issues && item.issues.length > 0 && (
                        <div className="item-section">
                          <div className="item-section-label">Problemas encontrados</div>
                          {item.issues.map((issue, idx) => {
                            const key = `${item.item_id}_${idx}`
                            const isResolved = resolved.has(key)
                            // `issue` pode ser string ou objeto {severity, description}
                            const issueText = typeof issue === 'string'
                              ? issue
                              : `${issue.severity ? `[${issue.severity.toUpperCase()}] ` : ''}${issue.description || ''}`
                            return (
                              <div key={idx} className={`issue-item${isResolved ? ' resolved' : ''}`}>
                                <span className="issue-text">{issueText}</span>
                                {!isResolved && evalId ? (
                                  <button className="btn btn-xs btn-resolve" onClick={() => handleResolve(item.item_id, idx)}>
                                    Resolvi
                                  </button>
                                ) : isResolved ? (
                                  <span className="resolved-badge">✓ Resolvido</span>
                                ) : null}
                              </div>
                            )
                          })}
                        </div>
                      )}
                      {item.suggestion && (
                        <div className="item-section">
                          <div className="item-section-label">Sugestão</div>
                          <div className="item-section-content suggestion-box">{item.suggestion}</div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
