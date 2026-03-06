import { useState, useEffect } from 'react'
import DOMPurify from 'dompurify'
import { useAuth } from '../context/AuthContext'
import { ArrowRight, CaretDown, CaretRight } from '@phosphor-icons/react'
import useCompanyStore from '../store/companyStore'

const FILTER_TABS = ['Todos', 'Adicionado', 'Removido', 'Modificado']

const CHANGE_CLASS = {
  added: 'change-added',
  removed: 'change-removed',
  modified: 'change-modified',
  unchanged: 'change-unchanged',
}

export default function DiffPage() {
  const { authHeaders } = useAuth()
  const { selectedCompany } = useCompanyStore()

  const [mode, setMode] = useState('local')
  const [activeTipo, setActiveTipo] = useState('Todos')
  // Modo local: arquivos já baixados da empresa
  const [localFiles, setLocalFiles] = useState([])
  const [doc1Local, setDoc1Local] = useState(null)
  const [doc2Local, setDoc2Local] = useState(null)
  // Modo upload
  const [file1, setFile1] = useState(null)
  const [file2, setFile2] = useState(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [activeFilter, setActiveFilter] = useState('Todos')
  const [expandedSections, setExpandedSections] = useState(new Set())

  useEffect(() => {
    setLocalFiles([])
    setDoc1Local(null)
    setDoc2Local(null)
    setResult(null)
    setActiveTipo('Todos')
    if (!selectedCompany?.cnpj) return
    fetch(`/api/archive/local-files?cnpj=${encodeURIComponent(selectedCompany.cnpj)}`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : { files: [] })
      .then(data => {
        const files = data.files || []
        setLocalFiles(files)
        if (files.length >= 2) {
          setDoc1Local(files[1]) // penúltimo
          setDoc2Local(files[0]) // mais recente
        } else if (files.length === 1) {
          setDoc1Local(files[0])
          setDoc2Local(files[0])
        }
      })
      .catch(() => {})
  }, [selectedCompany])

  const TIPO_TABS = ['Todos', 'FRE', 'DFP', 'FCA', 'IPE']
  const filteredLocalFiles = activeTipo === 'Todos'
    ? localFiles
    : localFiles.filter(f => (f.tipo_doc || 'FRE').toUpperCase() === activeTipo)

  async function handleCompare() {
    setError(''); setLoading(true); setResult(null)
    try {
      let res
      if (mode === 'local') {
        if (!doc1Local || !doc2Local) { setError('Selecione os dois documentos locais'); setLoading(false); return }
        if (!selectedCompany?.cnpj) { setError('Selecione uma empresa'); setLoading(false); return }
        res = await fetch('/api/diff/compare-local', {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            cnpj: selectedCompany.cnpj,
            doc1_filename: doc1Local.filename,
            doc2_filename: doc2Local.filename,
            include_semantic: true,
          }),
        })
      } else {
        if (!file1 || !file2) { setError('Selecione os dois arquivos'); setLoading(false); return }
        const fd = new FormData()
        fd.append('file1', file1); fd.append('file2', file2)
        res = await fetch('/api/diff/compare-upload', { method: 'POST', headers: authHeaders(), body: fd })
      }
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Erro na comparação')
      setResult(data)
      setExpandedSections(new Set())
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  function toggleSection(idx) {
    setExpandedSections(prev => {
      const n = new Set(prev)
      n.has(idx) ? n.delete(idx) : n.add(idx)
      return n
    })
  }

  // Backend retorna `sections` (não section_diffs)
  const sections = result?.sections || result?.section_diffs || []
  const filterMap = { 'Adicionado': 'added', 'Removido': 'removed', 'Modificado': 'modified' }
  const filtered = activeFilter === 'Todos' ? sections
    : sections.filter(s => s.change_type === filterMap[activeFilter])

  function fileLabel(f) {
    if (!f) return '—'
    return `${f.tipo_doc || 'DOC'} ${(f.dt_refer || '').slice(0, 4)} — ${f.filename}`
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Comparação de Versões</h1>
        <p className="page-subtitle">Identifique mudanças entre dois documentos e seu impacto</p>
      </div>

      <div className="card">
        <div className="mode-tabs">
          <button className={`mode-tab${mode === 'local' ? ' active' : ''}`} onClick={() => setMode('local')}>
            Arquivo Local
          </button>
          <button className={`mode-tab${mode === 'upload' ? ' active' : ''}`} onClick={() => setMode('upload')}>
            Upload de Arquivos
          </button>
        </div>

        {mode === 'local' && selectedCompany && localFiles.length > 0 && (
          <div className="filter-tabs" style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
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
                  setDoc1Local(next[1] || next[0] || null)
                  setDoc2Local(next[0] || null)
                }}
                type="button"
              >
                {t}
              </button>
            ))}
          </div>
        )}

        <div className="diff-selectors">
          {mode === 'local' ? (
            <>
              {!selectedCompany && (
                <div className="empty-hint" style={{ width: '100%' }}>
                  Selecione uma empresa na barra lateral.
                </div>
              )}
              {selectedCompany && localFiles.length === 0 && (
                <div className="empty-hint" style={{ width: '100%' }}>
                  Nenhum arquivo local. Baixe documentos na aba <strong>Empresas</strong>.
                </div>
              )}
              {selectedCompany && localFiles.length > 0 && (
                <>
                  <div className="form-group">
                    <label className="form-label">Documento Base</label>
                    <select className="form-select" value={doc1Local?.filename || ''}
                      onChange={e => setDoc1Local(filteredLocalFiles.find(f => f.filename === e.target.value))}>
                      {filteredLocalFiles.map(f => (
                        <option key={f.filename} value={f.filename}>{fileLabel(f)}</option>
                      ))}
                    </select>
                  </div>
                  <ArrowRight size={22} weight="duotone" className="diff-arrow" />
                  <div className="form-group">
                    <label className="form-label">Documento Novo</label>
                    <select className="form-select" value={doc2Local?.filename || ''}
                      onChange={e => setDoc2Local(filteredLocalFiles.find(f => f.filename === e.target.value))}>
                      {filteredLocalFiles.map(f => (
                        <option key={f.filename} value={f.filename}>{fileLabel(f)}</option>
                      ))}
                    </select>
                  </div>
                </>
              )}
            </>
          ) : (
            <>
              <div className="form-group">
                <label className="form-label">Arquivo Base</label>
                <input type="file" accept=".pdf" className="form-input" onChange={e => setFile1(e.target.files[0])} />
              </div>
              <ArrowRight size={22} weight="duotone" className="diff-arrow" />
              <div className="form-group">
                <label className="form-label">Arquivo Novo</label>
                <input type="file" accept=".pdf" className="form-input" onChange={e => setFile2(e.target.files[0])} />
              </div>
            </>
          )}
        </div>

        {error && <div className="alert alert-error">{error}</div>}
        <button
          className="btn btn-primary"
          onClick={handleCompare}
          disabled={loading || (mode === 'local' && (!doc1Local || !doc2Local || !selectedCompany))}
        >
          {loading ? 'Comparando...' : 'Comparar'}
        </button>
      </div>

      {result && (
        <div className="diff-results">
          <div className="diff-summary">
            <span>{sections.length} seções comparadas</span>
            <span className="diff-stat-added">+{sections.filter(s => s.change_type === 'added').length} adicionadas</span>
            <span className="diff-stat-removed">-{sections.filter(s => s.change_type === 'removed').length} removidas</span>
            <span className="diff-stat-modified">~{sections.filter(s => s.change_type === 'modified').length} modificadas</span>
          </div>

          <div className="filter-tabs">
            {FILTER_TABS.map(f => (
              <button key={f} className={`filter-tab${activeFilter === f ? ' active' : ''}`} onClick={() => setActiveFilter(f)}>
                {f}
              </button>
            ))}
          </div>

          <div className="sections-list">
            {filtered.length === 0 && <div className="empty-hint">Nenhuma seção para este filtro.</div>}
            {filtered.map((sec, idx) => (
              <div key={idx} className={`section-card ${CHANGE_CLASS[sec.change_type] || ''}`}>
                <button className="section-header" onClick={() => toggleSection(idx)}>
                  <span className="section-id">{sec.item_id}</span>
                  <span className="section-title">{sec.titulo_a || sec.titulo_b || sec.titulo || ''}</span>
                  <div className="section-header-right">
                    <span className={`change-badge change-badge-${sec.change_type}`}>{sec.change_type}</span>
                    {expandedSections.has(idx) ? <CaretDown size={16} weight="bold" /> : <CaretRight size={16} weight="bold" />}
                  </div>
                </button>

                {expandedSections.has(idx) && (
                  <div className="section-diff-content">
                    {sec.semantic_summary && (
                      <div className="semantic-summary"
                        dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(
                          sec.semantic_summary.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br/>')
                        ) }} />
                    )}
                    <div className="diff-panels">
                      <div className="diff-panel diff-panel-old">
                        <div className="diff-panel-label">Antes</div>
                        <pre className="diff-text">{sec.old_text || (sec.text_changes?.[0]?.old_text) || '(sem conteúdo)'}</pre>
                      </div>
                      <div className="diff-panel diff-panel-new">
                        <div className="diff-panel-label">Depois</div>
                        <pre className="diff-text">{sec.new_text || (sec.text_changes?.[0]?.new_text) || '(sem conteúdo)'}</pre>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
