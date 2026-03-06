import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { ArrowsClockwise, FileText, CalendarBlank } from '@phosphor-icons/react'
import useCompanyStore from '../store/companyStore'

const TIPO_TABS = ['Todos', 'FRE', 'DFP', 'FCA', 'IPE']

export default function ArchivePage() {
  const { authHeaders } = useAuth()
  const { selectedCompany } = useCompanyStore()
  const [documents, setDocuments] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeTipo, setActiveTipo] = useState('Todos')

  useEffect(() => {
    setSelected(null)
    setDocuments([])
    setActiveTipo('Todos')
    if (!selectedCompany?.cnpj) return
    loadDocuments()
  }, [selectedCompany])

  async function loadDocuments() {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(
        `/api/archive/local-files?cnpj=${encodeURIComponent(selectedCompany.cnpj)}`,
        { headers: authHeaders() }
      )
      if (res.ok) {
        const data = await res.json()
        setDocuments(data.files || [])
      } else {
        setError('Erro ao carregar documentos.')
      }
    } catch (err) {
      setError(err.message || 'Erro ao carregar documentos.')
    } finally {
      setLoading(false)
    }
  }

  function getPdfUrl(doc) {
    return `/api/archive/local-files/${encodeURIComponent(doc.filename)}/pdf?cnpj=${encodeURIComponent(selectedCompany.cnpj)}`
  }

  const filtered = activeTipo === 'Todos'
    ? documents
    : documents.filter(d => (d.tipo_doc || 'FRE').toUpperCase() === activeTipo)

  return (
    <div className="archive-layout">
      <aside className="archive-sidebar">
        <div className="archive-header">
          <span className="archive-title">Documentos</span>
          <button
            className="btn-icon"
            onClick={loadDocuments}
            disabled={loading || !selectedCompany}
            title="Atualizar"
          >
            <ArrowsClockwise size={18} weight="duotone" className={loading ? 'spin' : ''} />
          </button>
        </div>

        {/* Filtro por tipo */}
        <div className="filter-tabs" style={{ padding: '0 8px 4px', flexWrap: 'wrap', gap: '4px' }}>
          {TIPO_TABS.map(t => (
            <button
              key={t}
              className={`filter-tab${activeTipo === t ? ' active' : ''}`}
              style={{ fontSize: '0.75rem', padding: '2px 8px' }}
              onClick={() => setActiveTipo(t)}
            >
              {t}
            </button>
          ))}
        </div>

        {error && <div className="alert alert-error alert-sm">{error}</div>}
        {loading && <div className="loading-hint">Carregando...</div>}

        {!loading && !selectedCompany && (
          <div className="empty-hint">Selecione uma empresa na barra lateral.</div>
        )}

        {!loading && selectedCompany && filtered.length === 0 && (
          <div className="empty-hint">
            Nenhum documento{activeTipo !== 'Todos' ? ` ${activeTipo}` : ''}.<br />
            Baixe na aba <strong>Empresas</strong>.
          </div>
        )}

        {filtered.map(doc => (
          <button
            key={doc.filename}
            className={`archive-item${selected?.filename === doc.filename ? ' active' : ''}`}
            onClick={() => setSelected(doc)}
          >
            <FileText size={18} weight="duotone" />
            <div className="archive-item-info">
              <div className="archive-item-title">
                {doc.tipo_doc || 'FRE'} {(doc.dt_refer || '').slice(0, 4)}
              </div>
              <div className="archive-item-meta">
                <CalendarBlank size={13} weight="duotone" />
                {doc.dt_refer || '—'} · v{doc.versao || 1}
              </div>
            </div>
          </button>
        ))}
      </aside>

      <div className="archive-viewer">
        {selected ? (
          <iframe
            key={selected.filename}
            src={getPdfUrl(selected)}
            className="pdf-iframe"
            title={`${selected.tipo_doc || 'DOC'} ${selected.dt_refer}`}
          />
        ) : (
          <div className="viewer-empty">
            <FileText size={56} weight="duotone" style={{ opacity: 0.2 }} />
            <h3>Selecione um documento</h3>
            <p>Escolha na lista à esquerda para visualizar aqui.</p>
          </div>
        )}
      </div>
    </div>
  )
}
