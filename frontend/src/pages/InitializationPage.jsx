import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import useCompanyStore from '../store/companyStore'
import {
  RocketLaunch, Buildings, ArrowsClockwise, Plus, X,
  MagnifyingGlass, CheckCircle, Warning, DownloadSimple, Trash,
  MagnifyingGlassPlus, Robot, Database, Folder, CircleNotch,
  UploadSimple,
} from '@phosphor-icons/react'

const CURRENT_YEAR = new Date().getFullYear()

export default function InitializationPage() {
  const { authHeaders } = useAuth()
  const { setSelectedCompany } = useCompanyStore()

  const [status, setStatus] = useState(null)
  const [warming, setWarming] = useState(false)
  const [warmProgress, setWarmProgress] = useState(null)

  const [showAddModal, setShowAddModal] = useState(false)
  const [addQuery, setAddQuery] = useState('')
  const [addResults, setAddResults] = useState([])
  const [addSearching, setAddSearching] = useState(false)
  const [adding, setAdding] = useState(false)
  const [addStatus, setAddStatus] = useState(null)

  // Sync de documentos após adicionar empresa
  const [syncing, setSyncing] = useState(null)   // null | {cnpj, name}
  const [syncProgress, setSyncProgress] = useState(null)

  const [uploadCompany, setUploadCompany] = useState(null)  // {cnpj, name} | null

  const debounceRef = useRef(null)

  useEffect(() => { fetchStatus() }, [])

  async function fetchStatus() {
    try {
      const res = await fetch('/api/cvm/status', { headers: authHeaders() })
      if (res.ok) setStatus(await res.json())
    } catch {
      setStatus({ initialized: false, local_companies: [] })
    }
  }

  async function startWarm(force = false) {
    setWarming(true)
    setWarmProgress({ done: 0, total: 20, current: '', log: [] })
    try {
      const res = await fetch(`/api/cvm/cache/warm?force=${force}`, {
        method: 'POST',
        headers: authHeaders(),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value)
        for (const line of text.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(line.slice(6))
            setWarmProgress(prev => ({
              done: ev.done,
              total: ev.total,
              current: ev.current || '',
              log: ev.complete ? prev.log : [...(prev?.log || []), ev.current],
            }))
          } catch { /* ignore malformed event */ }
        }
      }
    } catch (err) {
      console.error('Erro ao baixar dados CVM:', err)
    }
    setWarming(false)
    await fetchStatus()
  }

  function openAddModal() {
    setShowAddModal(true)
    setAddQuery('')
    setAddResults([])
    setAddStatus(null)
    setAdding(false)
  }

  function closeAddModal() {
    setShowAddModal(false)
    fetchStatus()
  }

  function handleAddInput(e) {
    const val = e.target.value
    setAddQuery(val)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => searchForAdd(val), 300)
  }

  async function searchForAdd(q) {
    if (!q.trim()) { setAddResults([]); return }
    setAddSearching(true)
    try {
      const res = await fetch(
        `/api/cvm/companies/search?q=${encodeURIComponent(q)}&year=${CURRENT_YEAR}`,
        { headers: authHeaders() }
      )
      if (res.ok) {
        const data = await res.json()
        setAddResults(data.results || [])
      }
    } catch { setAddResults([]) }
    finally { setAddSearching(false) }
  }

  async function handleAddCompany(c) {
    setAdding(true)
    setAddStatus(null)
    try {
      const res = await fetch('/api/cvm/companies/add', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ cnpj: c.cnpj, name: c.name }),
      })
      const data = await res.json()
      if (data.ok) {
        // Fecha modal e inicia download dos documentos
        setShowAddModal(false)
        setAdding(false)
        await startSync(c)
        return
      } else {
        setAddStatus({ ok: false, message: 'Erro ao adicionar empresa.' })
      }
    } catch (err) {
      setAddStatus({ ok: false, message: `Erro: ${err.message}` })
    }
    setAdding(false)
  }

  async function startSync(c) {
    setSelectedCompany({ cnpj: c.cnpj, name: c.name })
    setSyncing({ cnpj: c.cnpj, name: c.name })
    setSyncProgress({ starting: true, done: 0, total: 0, current: '', saved: 0, errors: 0, skipped: 0, log: [] })
    try {
      const res = await fetch('/api/cvm/companies/sync', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ cnpj: c.cnpj, name: c.name }),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value)
        for (const line of text.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(line.slice(6))
            setSyncProgress(prev => ({
              starting: ev.starting ?? false,
              done: ev.done ?? prev.done,
              total: ev.total ?? prev.total,
              current: ev.current || prev.current,
              saved: ev.saved ?? prev.saved,
              errors: ev.errors ?? prev.errors,
              skipped: ev.skipped_existing ?? ev.skipped ?? prev.skipped,
              complete: ev.complete ?? false,
              log: ev.ok === true ? [...(prev?.log || []), ev.current] : (prev?.log || []),
            }))
          } catch { /* ignorar evento malformado */ }
        }
      }
    } catch (err) {
      console.error('Erro ao sincronizar documentos:', err)
    }
    await fetchStatus()
    // Mantém tela de conclusão por 2s antes de voltar
    setTimeout(() => {
      setSyncing(null)
      setSyncProgress(null)
    }, 2500)
  }

  // ── Loading inicial ────────────────────────────────────────────────────────
  if (status === null) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        <ArrowsClockwise size={28} weight="duotone" className="spin" />
      </div>
    )
  }

  // ── Tela de sync de documentos ────────────────────────────────────────────
  if (syncing) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '24px', padding: '40px' }}>
        {syncProgress?.complete ? (
          <CheckCircle size={52} weight="duotone" style={{ color: 'var(--primary)' }} />
        ) : (
          <DownloadSimple size={48} weight="duotone" style={{ color: 'var(--primary)', opacity: 0.7 }} className="spin" />
        )}
        <div style={{ textAlign: 'center' }}>
          <h2 style={{ margin: '0 0 6px', fontSize: '1.2rem', fontWeight: 700, color: 'var(--text)' }}>
            {syncProgress?.complete ? 'Download concluído!' : `Baixando documentos de ${syncing.name}...`}
          </h2>
          {syncProgress?.complete ? (
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              {syncProgress.saved} arquivo(s) salvos
              {syncProgress.skipped > 0 && ` · ${syncProgress.skipped} já existiam`}
              {syncProgress.errors > 0 && ` · ${syncProgress.errors} erro(s)`}
            </p>
          ) : syncProgress?.starting && syncProgress?.total === 0 ? (
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              Buscando documentos disponíveis...
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
              <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                Última versão por documento · sem duplicatas · downloads em paralelo
              </p>
              <p style={{ margin: 0, fontSize: '0.8rem', color: '#f59e0b', fontWeight: 500 }}>
                ⚠ Este processo pode demorar vários minutos dependendo do volume de documentos
              </p>
            </div>
          )}
        </div>
        {!syncProgress?.complete && <SyncProgress progress={syncProgress} />}
      </div>
    )
  }

  // ── Tela de carregamento (download de CSVs) ────────────────────────────────
  if (warming) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '24px', padding: '40px' }}>
        <ArrowsClockwise size={48} weight="duotone" style={{ color: 'var(--primary)', opacity: 0.6 }} className="spin" />
        <div style={{ textAlign: 'center' }}>
          <h2 style={{ margin: '0 0 6px', fontSize: '1.2rem', fontWeight: 700, color: 'var(--text)' }}>
            Baixando dados da CVM...
          </h2>
          <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Isso pode levar alguns minutos na primeira vez.
          </p>
        </div>
        <WarmProgress progress={warmProgress} />
      </div>
    )
  }

  const isInitialized = status.initialized
  const companies = status.local_companies || []

  // ── Configuração Inicial ───────────────────────────────────────────────────
  if (!isInitialized && companies.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '20px', padding: '40px' }}>
        <RocketLaunch size={64} weight="duotone" style={{ color: 'var(--primary)', opacity: 0.3 }} />
        <div style={{ textAlign: 'center' }}>
          <h2 style={{ margin: '0 0 8px', fontSize: '1.3rem', fontWeight: 700, color: 'var(--text)' }}>
            Configuração Inicial
          </h2>
          <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.9rem', maxWidth: '380px' }}>
            Baixe os dados da CVM para habilitar buscas e adicionar empresas ao sistema.
          </p>
        </div>
        <button
          className="btn-primary"
          onClick={() => startWarm(false)}
          style={{ fontSize: '0.95rem', padding: '10px 28px', display: 'flex', alignItems: 'center', gap: '8px' }}
        >
          <RocketLaunch size={18} weight="duotone" />
          Iniciar Configuração
        </button>
      </div>
    )
  }

  // ── Tela Principal ─────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{
        padding: '16px 24px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <RocketLaunch size={20} weight="duotone" style={{ color: 'var(--primary)' }} />
          <span style={{ fontWeight: 600, fontSize: '1rem' }}>Inicialização</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className="btn-secondary"
            onClick={() => startWarm(true)}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem' }}
          >
            <ArrowsClockwise size={15} weight="duotone" />
            Atualizar Dados
          </button>
          <button
            className="btn-primary"
            onClick={openAddModal}
            disabled={!isInitialized}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem' }}
          >
            <Plus size={15} weight="bold" />
            Adicionar Empresa
          </button>
        </div>
      </div>

      {/* Empresas */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
        <div style={{ marginBottom: '16px', fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-muted)' }}>
          EMPRESAS ADICIONADAS ({companies.length})
        </div>

        {companies.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            <Buildings size={40} weight="duotone" style={{ opacity: 0.25, display: 'block', margin: '0 auto 12px' }} />
            Nenhuma empresa adicionada.<br />
            Use "Adicionar Empresa" para começar.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {companies.map(c => (
              <CompanyCard
                key={c.cnpj}
                company={c}
                authHeaders={authHeaders}
                onDeleted={() => fetchStatus()}
                onUpload={() => setUploadCompany({ cnpj: c.cnpj, name: c.name })}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modal de adicionar empresa */}
      {showAddModal && (
        <AddModal
          query={addQuery}
          results={addResults}
          searching={addSearching}
          adding={adding}
          addStatus={addStatus}
          onInput={handleAddInput}
          onAdd={handleAddCompany}
          onClose={closeAddModal}
        />
      )}

      {/* Modal de upload manual */}
      {uploadCompany && (
        <UploadDocModal
          company={uploadCompany}
          authHeaders={authHeaders}
          onClose={() => setUploadCompany(null)}
        />
      )}
    </div>
  )
}

// ── Componentes auxiliares ─────────────────────────────────────────────────

function WarmProgress({ progress }) {
  if (!progress) return null
  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0
  return (
    <div style={{ width: '100%', maxWidth: '440px', textAlign: 'center' }}>
      {/* Barra de progresso */}
      <div style={{
        height: '8px', borderRadius: '4px', background: 'var(--border)',
        overflow: 'hidden', marginBottom: '10px',
      }}>
        <div style={{
          height: '100%', width: `${pct}%`, background: 'var(--primary)',
          borderRadius: '4px', transition: 'width 0.4s ease',
        }} />
      </div>

      {/* Contadores */}
      <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', display: 'flex', justifyContent: 'center', gap: '16px', marginBottom: '6px' }}>
        <span style={{ fontWeight: 600, color: 'var(--text)' }}>{pct}%</span>
        <span>{progress.done}/{progress.total} arquivos</span>
        {progress.current && <span style={{ fontStyle: 'italic' }}>{progress.current}...</span>}
      </div>

      {/* Log de concluídos */}
      {progress.log.length > 0 && (
        <div style={{ marginTop: '14px', maxHeight: '130px', overflowY: 'auto', fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', flexWrap: 'wrap', gap: '4px', justifyContent: 'center' }}>
          {progress.log.map((item, i) => (
            <span key={i} style={{ padding: '2px 7px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '4px' }}>
              {item} ✓
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function SyncProgress({ progress }) {
  if (!progress || progress.total === 0) return (
    <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
      <ArrowsClockwise size={16} weight="duotone" className="spin" />
      Identificando documentos...
    </div>
  )
  const pct = Math.round((progress.done / progress.total) * 100)
  return (
    <div style={{ width: '100%', maxWidth: '440px', textAlign: 'center' }}>
      <div style={{ height: '8px', borderRadius: '4px', background: 'var(--border)', overflow: 'hidden', marginBottom: '10px' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: 'var(--primary)', borderRadius: '4px', transition: 'width 0.4s ease' }} />
      </div>
      <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', display: 'flex', justifyContent: 'center', gap: '16px', marginBottom: '6px' }}>
        <span style={{ fontWeight: 600, color: 'var(--text)' }}>{pct}%</span>
        <span>{progress.done}/{progress.total} documentos</span>
        {progress.current && <span style={{ fontStyle: 'italic' }}>{progress.current}</span>}
      </div>
      {progress.errors > 0 && (
        <div style={{ fontSize: '0.75rem', color: '#dc2626' }}>{progress.errors} erro(s)</div>
      )}
      {progress.log?.length > 0 && (
        <div style={{ marginTop: '14px', maxHeight: '130px', overflowY: 'auto', fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', flexWrap: 'wrap', gap: '4px', justifyContent: 'center' }}>
          {progress.log.map((item, i) => (
            <span key={i} style={{ padding: '2px 7px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '4px' }}>
              {item} ✓
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function CompanyCard({ company, authHeaders, onDeleted, onUpload }) {
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const c = company.doc_counts || {}

  return (
    <>
      <div style={{
        display: 'flex', alignItems: 'center', gap: '14px',
        padding: '14px 16px', borderRadius: '10px',
        background: 'var(--surface)', border: '1px solid var(--border)',
      }}>
        <Buildings size={28} weight="duotone" style={{ color: 'var(--primary)', flexShrink: 0, opacity: 0.7 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text)', marginBottom: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {company.name}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'monospace', marginBottom: '4px' }}>
            {company.cnpj}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', gap: '10px' }}>
            {['FRE', 'DFP', 'FCA', 'IPE'].map(t => (
              <span key={t}><strong style={{ color: 'var(--text)' }}>{c[t] ?? 0}</strong> {t}</span>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
          <button
            onClick={onUpload}
            title="Carregar PDF manualmente"
            style={{
              background: 'none', border: '1px solid var(--border)', borderRadius: '6px',
              padding: '6px 8px', cursor: 'pointer',
              color: 'var(--text-secondary)',
              display: 'flex', alignItems: 'center', gap: '4px',
              fontSize: '0.8rem',
              transition: 'background 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover, #f3f4f6)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
          >
            <UploadSimple size={14} weight="duotone" />
            Carregar PDF
          </button>
          <button
            onClick={() => setShowDeleteModal(true)}
            title="Remover empresa"
            style={{
              background: 'none', border: '1px solid var(--border)', borderRadius: '6px',
              padding: '6px 8px', cursor: 'pointer',
              color: '#dc2626',
              display: 'flex', alignItems: 'center', gap: '4px',
              fontSize: '0.8rem',
              transition: 'background 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = '#fef2f2' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
          >
            <Trash size={14} weight="duotone" />
            Remover
          </button>
        </div>
      </div>

      {showDeleteModal && (
        <DeleteModal
          company={company}
          authHeaders={authHeaders}
          onClose={() => setShowDeleteModal(false)}
          onDeleted={() => { setShowDeleteModal(false); onDeleted() }}
        />
      )}
    </>
  )
}

// Ícone por etapa
const STEP_ICONS = {
  lookup: MagnifyingGlassPlus,
  openai: Robot,
  db: Database,
  local: Folder,
}

const STEP_LABELS_DEFAULT = {
  lookup: 'Buscando registros',
  openai: 'Dados OpenAI',
  db: 'Banco de dados',
  local: 'Arquivos locais',
}

function DeleteModal({ company, authHeaders, onClose, onDeleted }) {
  // phase: 'confirm' | 'progress' | 'done'
  const [phase, setPhase] = useState('confirm')
  const [steps, setSteps] = useState({
    lookup: { status: 'pending', label: STEP_LABELS_DEFAULT.lookup, detail: '' },
    openai: { status: 'pending', label: STEP_LABELS_DEFAULT.openai, detail: '' },
    db:     { status: 'pending', label: STEP_LABELS_DEFAULT.db,     detail: '' },
    local:  { status: 'pending', label: STEP_LABELS_DEFAULT.local,  detail: '' },
  })
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)

  async function startDelete() {
    setPhase('progress')
    setError(null)
    try {
      const res = await fetch('/api/cvm/companies/delete-stream', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ cnpj: company.cnpj }),
      })
      if (!res.ok) { setError('Erro ao iniciar remoção.'); return }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value)
        for (const line of text.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(line.slice(6))
            if (ev.step === 'complete') {
              setSummary(ev)
              setPhase('done')
            } else if (ev.step) {
              setSteps(prev => ({
                ...prev,
                [ev.step]: { status: ev.status, label: ev.label, detail: ev.detail || '' },
              }))
            }
          } catch { /* ignorar evento malformado */ }
        }
      }
    } catch (err) {
      setError(`Erro: ${err.message}`)
    }
  }

  const stepOrder = ['lookup', 'openai', 'db', 'local']

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'transparent',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100,
    }}>
      <div style={{
        background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: '14px',
        width: '440px', maxWidth: '95vw', boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Trash size={18} weight="duotone" style={{ color: '#dc2626' }} />
            <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Remover Empresa</span>
          </div>
          {phase !== 'progress' && (
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: '4px' }}>
              <X size={18} />
            </button>
          )}
        </div>

        {/* Body */}
        <div style={{ padding: '20px' }}>
          {/* Empresa info */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            padding: '10px 12px', borderRadius: '8px',
            background: 'var(--surface)', border: '1px solid var(--border)',
            marginBottom: '20px',
          }}>
            <Buildings size={22} weight="duotone" style={{ color: 'var(--primary)', opacity: 0.7, flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--text)' }}>{company.name}</div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>{company.cnpj}</div>
            </div>
          </div>

          {/* Fase: confirm */}
          {phase === 'confirm' && (
            <>
              <p style={{ margin: '0 0 16px', fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                Esta ação irá remover permanentemente todos os dados desta empresa:
              </p>
              <ul style={{ margin: '0 0 20px', paddingLeft: '18px', fontSize: '0.83rem', color: 'var(--text-muted)', lineHeight: 2 }}>
                <li>Documentos PDF e índices locais</li>
                <li>Registros do banco de dados (avaliações, diff, chat)</li>
                <li>Vector stores e arquivos no OpenAI</li>
              </ul>
              {error && (
                <div style={{ padding: '8px 12px', borderRadius: '8px', background: '#fef2f2', border: '1px solid #fca5a5', color: '#dc2626', fontSize: '0.82rem', marginBottom: '14px' }}>
                  {error}
                </div>
              )}
              <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                <button
                  onClick={onClose}
                  style={{
                    fontSize: '0.85rem', padding: '7px 18px', borderRadius: '8px',
                    background: 'none', color: 'var(--text-muted)',
                    border: '1px solid var(--border)', cursor: 'pointer',
                  }}
                >
                  Cancelar
                </button>
                <button
                  onClick={startDelete}
                  style={{
                    fontSize: '0.85rem', padding: '7px 18px', borderRadius: '8px',
                    background: '#dc2626', color: '#fff', border: 'none', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600,
                  }}
                >
                  <Trash size={14} weight="duotone" />
                  Confirmar Remoção
                </button>
              </div>
            </>
          )}

          {/* Fase: progress */}
          {(phase === 'progress' || phase === 'done') && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {stepOrder.map(key => {
                const step = steps[key]
                const Icon = STEP_ICONS[key]
                const isDone = step.status === 'done'
                const isRunning = step.status === 'running'
                const isPending = step.status === 'pending'
                return (
                  <div key={key} style={{
                    display: 'flex', alignItems: 'flex-start', gap: '12px',
                    padding: '10px 12px', borderRadius: '8px',
                    background: isDone ? '#f0fdf4' : isPending ? 'var(--surface)' : '#fffbeb',
                    border: `1px solid ${isDone ? '#86efac' : isPending ? 'var(--border)' : '#fcd34d'}`,
                    transition: 'all 0.3s ease',
                  }}>
                    {/* Status indicator */}
                    <div style={{ flexShrink: 0, marginTop: '1px' }}>
                      {isDone
                        ? <CheckCircle size={18} weight="duotone" style={{ color: '#16a34a' }} />
                        : isRunning
                          ? <CircleNotch size={18} weight="bold" className="spin" style={{ color: '#d97706' }} />
                          : <Icon size={18} weight="duotone" style={{ color: 'var(--text-muted)', opacity: 0.4 }} />
                      }
                    </div>
                    {/* Text */}
                    <div style={{ flex: 1 }}>
                      <div style={{
                        fontSize: '0.83rem', fontWeight: isDone || isRunning ? 600 : 400,
                        color: isDone ? '#15803d' : isRunning ? '#92400e' : 'var(--text-muted)',
                      }}>
                        {step.label}
                      </div>
                      {step.detail && (
                        <div style={{ fontSize: '0.73rem', color: isDone ? '#16a34a' : 'var(--text-muted)', marginTop: '2px' }}>
                          {step.detail}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}

              {/* Resumo final */}
              {phase === 'done' && summary && (
                <div style={{
                  marginTop: '6px', padding: '12px 14px', borderRadius: '8px',
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.8,
                }}>
                  <div style={{ fontWeight: 700, color: 'var(--text)', marginBottom: '4px' }}>Resumo da remoção</div>
                  <div>{summary.deleted_docs} documento(s) do banco</div>
                  <div>{summary.deleted_vs} vector store(s) OpenAI</div>
                  <div>{summary.deleted_files} arquivo(s) OpenAI</div>
                  <div>{summary.deleted_local} arquivo(s) local(is)</div>
                </div>
              )}

              {error && (
                <div style={{ padding: '8px 12px', borderRadius: '8px', background: '#fef2f2', border: '1px solid #fca5a5', color: '#dc2626', fontSize: '0.82rem' }}>
                  {error}
                </div>
              )}

              {phase === 'done' && (
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
                  <button className="btn-primary" onClick={onDeleted} style={{ fontSize: '0.85rem' }}>
                    Fechar
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function UploadDocModal({ company, authHeaders, onClose }) {
  const [tipoDoc, setTipoDoc] = useState('FRE')
  const [dtRefer, setDtRefer] = useState('')
  const [versao, setVersao] = useState('1')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  async function handleUpload() {
    if (!file) { setError('Selecione um arquivo PDF.'); return }
    if (!dtRefer) { setError('Informe a data de referência.'); return }
    setError('')
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('cnpj', company.cnpj)
      fd.append('tipo_doc', tipoDoc)
      fd.append('dt_refer', dtRefer)
      fd.append('versao', versao)
      fd.append('file', file)
      const res = await fetch('/api/archive/local-files/upload', {
        method: 'POST',
        headers: authHeaders(),
        body: fd,
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Erro ao enviar arquivo.'); return }
      setSuccess(true)
    } catch (err) {
      setError(`Erro: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const TIPO_COLORS = { FRE: '#3b82f6', DFP: '#22c55e', FCA: '#a855f7', IPE: '#f97316' }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'transparent', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{
        background: 'var(--card)', border: '1px solid var(--border)', borderRadius: '12px',
        padding: '24px', width: '100%', maxWidth: '420px', boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text)' }}>
            Carregar PDF Manualmente
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}>
            <X size={18} weight="bold" />
          </button>
        </div>

        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
          {company.name} · <span style={{ fontFamily: 'monospace' }}>{company.cnpj}</span>
        </div>

        {success ? (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <CheckCircle size={40} weight="duotone" style={{ color: '#22c55e', display: 'block', margin: '0 auto 10px' }} />
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Arquivo enviado com sucesso!</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 16 }}>
              Já disponível na tela de Avaliação e Comparação.
            </div>
            <button className="btn btn-primary" onClick={onClose}>Fechar</button>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>
                Tipo de Documento
              </label>
              <div style={{ display: 'flex', gap: '6px' }}>
                {['FRE', 'DFP', 'FCA', 'IPE'].map(t => (
                  <button key={t} onClick={() => setTipoDoc(t)} style={{
                    padding: '3px 12px', borderRadius: 12, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                    border: '1px solid var(--border)',
                    background: tipoDoc === t ? (TIPO_COLORS[t]) : 'transparent',
                    color: tipoDoc === t ? '#fff' : 'var(--text-secondary)',
                  }}>{t}</button>
                ))}
              </div>
            </div>

            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>
                Data de Referência
              </label>
              <input
                type="date"
                className="input-field"
                value={dtRefer}
                onChange={e => setDtRefer(e.target.value)}
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>
                Versão
              </label>
              <input
                type="number"
                className="input-field"
                value={versao}
                min="1"
                onChange={e => setVersao(e.target.value)}
                style={{ width: '80px' }}
              />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 6 }}>
                Arquivo PDF
              </label>
              <input
                type="file"
                accept=".pdf"
                onChange={e => setFile(e.target.files[0] || null)}
                style={{ width: '100%', fontSize: '0.85rem' }}
              />
              {file && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
                  {file.name} ({(file.size / 1024 / 1024).toFixed(1)} MB)
                </div>
              )}
            </div>

            {error && (
              <div style={{ fontSize: '0.8rem', color: '#dc2626', marginBottom: '12px', padding: '8px 10px', background: '#fef2f2', borderRadius: 6 }}>
                {error}
              </div>
            )}

            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button onClick={onClose} style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 6, padding: '7px 16px', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Cancelar
              </button>
              <button className="btn btn-primary" onClick={handleUpload} disabled={loading}>
                {loading ? 'Enviando...' : 'Enviar'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}


function AddModal({ query, results, searching, adding, addStatus, onInput, onAdd, onClose }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'transparent',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        background: 'var(--bg)', border: '1px solid var(--border)',
        borderRadius: '12px', width: '460px', maxWidth: '95vw',
        maxHeight: '80vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
      }}>
        {/* Modal header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Adicionar Empresa</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: '4px' }}>
            <X size={18} />
          </button>
        </div>

        {/* Search input */}
        <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <div style={{ position: 'relative' }}>
            <MagnifyingGlass
              size={15}
              style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }}
            />
            <input
              className="input-field"
              style={{ width: '100%', paddingLeft: '32px', boxSizing: 'border-box' }}
              placeholder="Buscar empresa por nome ou CNPJ..."
              value={query}
              onChange={onInput}
              autoFocus
            />
          </div>
        </div>

        {/* Status feedback */}
        {addStatus && (
          <div style={{
            margin: '12px 20px 0', padding: '10px 12px', borderRadius: '8px', flexShrink: 0,
            background: addStatus.ok ? '#f0fdf4' : '#fef2f2',
            border: `1px solid ${addStatus.ok ? '#86efac' : '#fca5a5'}`,
            display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem',
            color: addStatus.ok ? '#16a34a' : '#dc2626',
          }}>
            {addStatus.ok
              ? <CheckCircle size={16} weight="duotone" />
              : <Warning size={16} weight="duotone" />}
            {addStatus.message}
          </div>
        )}

        {/* Adding spinner */}
        {adding && (
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            <ArrowsClockwise size={16} weight="duotone" className="spin" />
            Buscando documentos...
          </div>
        )}

        {/* Results */}
        {!adding && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 12px' }}>
            {searching && (
              <div style={{ padding: '12px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>Buscando...</div>
            )}
            {!searching && query && results.length === 0 && (
              <div style={{ padding: '12px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>Nenhuma empresa encontrada.</div>
            )}
            {!searching && !query && (
              <div style={{ padding: '12px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>Digite o nome ou CNPJ para buscar.</div>
            )}
            {results.map(c => (
              <button
                key={c.cnpj}
                onClick={() => onAdd(c)}
                style={{
                  width: '100%', textAlign: 'left', background: 'none',
                  border: 'none', borderRadius: '8px', padding: '10px 12px',
                  cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: '2px',
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--hover-bg, #f9fafb)'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}
              >
                <span style={{ fontSize: '0.85rem', fontWeight: 500, color: 'var(--text)' }}>{c.name}</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>{c.cnpj}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
