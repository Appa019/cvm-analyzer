import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import {
  CheckCircle, XCircle, HardDrives, Key, UserCircle,
  FloppyDisk, Eye, EyeSlash, ArrowsClockwise
} from '@phosphor-icons/react'

export default function SettingsPage() {
  const { authHeaders, user } = useAuth()
  const [appSettings, setAppSettings] = useState(null)
  const [health, setHealth] = useState(null)
  const [envSettings, setEnvSettings] = useState(null)
  const [loading, setLoading] = useState(true)

  // OpenAI card state
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [modelInput, setModelInput] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [savingEnv, setSavingEnv] = useState(false)
  const [envMsg, setEnvMsg] = useState(null) // { type: 'ok'|'error', text }

  // Refresh cards state
  const [refreshingChecklist, setRefreshingChecklist] = useState(false)
  const [refreshingCvm, setRefreshingCvm] = useState(false)
  const [checklistMsg, setChecklistMsg] = useState(null)
  const [cvmMsg, setCvmMsg] = useState(null)

  useEffect(() => {
    Promise.all([
      fetch('/api/settings/app', { headers: authHeaders() }).then(r => r.ok ? r.json() : null),
      fetch('/api/settings/health', { headers: authHeaders() }).then(r => r.ok ? r.json() : null),
      fetch('/api/settings/env', { headers: authHeaders() }).then(r => r.ok ? r.json() : null),
    ]).then(([app, h, env]) => {
      setAppSettings(app)
      setHealth(h)
      setEnvSettings(env)
      if (env) {
        setApiKeyInput('')
        setModelInput(env.openai_model || '')
      }
    }).finally(() => setLoading(false))
  }, [])

  async function handleSaveEnv(e) {
    e.preventDefault()
    setSavingEnv(true)
    setEnvMsg(null)
    try {
      const body = {}
      if (apiKeyInput.trim()) body.openai_api_key = apiKeyInput.trim()
      if (modelInput.trim()) body.openai_model = modelInput.trim()
      if (Object.keys(body).length === 0) {
        setEnvMsg({ type: 'error', text: 'Nenhum valor alterado.' })
        return
      }
      const res = await fetch('/api/settings/env', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (res.ok) {
        setEnvMsg({ type: 'ok', text: data.message })
        setApiKeyInput('')
        const updated = await fetch('/api/settings/env', { headers: authHeaders() }).then(r => r.json())
        setEnvSettings(updated)
      } else {
        setEnvMsg({ type: 'error', text: data.detail || 'Erro ao salvar.' })
      }
    } catch {
      setEnvMsg({ type: 'error', text: 'Erro de rede.' })
    } finally {
      setSavingEnv(false)
    }
  }

  async function handleRefreshChecklist() {
    setRefreshingChecklist(true)
    setChecklistMsg(null)
    try {
      const res = await fetch('/api/settings/refresh-checklist', {
        method: 'POST',
        headers: authHeaders(),
      })
      const data = await res.json()
      setChecklistMsg({ type: res.ok ? 'ok' : 'error', text: data.message || data.detail })
    } catch {
      setChecklistMsg({ type: 'error', text: 'Erro de rede.' })
    } finally {
      setRefreshingChecklist(false)
    }
  }

  async function handleRefreshCvm() {
    setRefreshingCvm(true)
    setCvmMsg(null)
    try {
      const res = await fetch('/api/settings/refresh-cvm', {
        method: 'POST',
        headers: authHeaders(),
      })
      const data = await res.json()
      setCvmMsg({ type: res.ok ? 'ok' : 'error', text: data.message || data.detail })
    } catch {
      setCvmMsg({ type: 'error', text: 'Erro de rede.' })
    } finally {
      setRefreshingCvm(false)
    }
  }

  if (loading) return <div className="page-container"><div className="loading-hint">Carregando...</div></div>

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Configurações</h1>
        <p className="page-subtitle">Status do sistema e configurações da conta</p>
      </div>

      {/* Status do Sistema */}
      <div className="card">
        <div className="card-title"><HardDrives size={18} weight="duotone" /> Status do Sistema</div>
        {health ? (
          <>
            <div className="settings-row">
              <span>API</span>
              <span className={`settings-status ${health.status === 'ok' ? 'ok' : 'error'}`}>
                {health.status === 'ok' ? <CheckCircle size={16} weight="duotone" /> : <XCircle size={16} weight="duotone" />}
                {health.status}
              </span>
            </div>
            <div className="settings-row">
              <span><Key size={16} weight="duotone" /> Chave OpenAI</span>
              <span className={`settings-status ${health.api_key_configured ? 'ok' : 'error'}`}>
                {health.api_key_configured
                  ? <><CheckCircle size={16} weight="duotone" /> Configurada</>
                  : <><XCircle size={16} weight="duotone" /> Não configurada</>}
              </span>
            </div>
          </>
        ) : <div className="empty-hint">Não foi possível carregar o status.</div>}
      </div>

      {/* OpenAI */}
      <div className="card">
        <div className="card-title"><Key size={18} weight="duotone" /> OpenAI</div>
        {envSettings && (
          <div className="settings-row" style={{ marginBottom: '1rem' }}>
            <span className="settings-label">Chave atual</span>
            <span className="settings-value" style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
              {envSettings.openai_api_key_masked || <em style={{ color: '#9ca3af' }}>não configurada</em>}
            </span>
          </div>
        )}
        <form onSubmit={handleSaveEnv}>
          <div style={{ marginBottom: '0.75rem' }}>
            <label className="settings-label" style={{ display: 'block', marginBottom: '0.4rem' }}>
              Nova API Key
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showKey ? 'text' : 'password'}
                className="input-field"
                placeholder="sk-proj-..."
                value={apiKeyInput}
                onChange={e => setApiKeyInput(e.target.value)}
                style={{ width: '100%', paddingRight: '2.5rem', boxSizing: 'border-box' }}
              />
              <button
                type="button"
                onClick={() => setShowKey(v => !v)}
                style={{ position: 'absolute', right: '0.6rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 0 }}
              >
                {showKey ? <EyeSlash size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <div style={{ marginBottom: '0.75rem' }}>
            <label className="settings-label" style={{ display: 'block', marginBottom: '0.4rem' }}>
              Modelo OpenAI
            </label>
            <select
              className="input-field"
              value={modelInput}
              onChange={e => setModelInput(e.target.value)}
              style={{ width: '100%', boxSizing: 'border-box' }}
            >
              <option value="gpt-4.1">GPT-4.1 (rápido, econômico)</option>
              <option value="gpt-4.1-mini">GPT-4.1 Mini (mais econômico)</option>
              <option value="gpt-5">GPT-5 (mais capaz)</option>
              <option value="gpt-5.4">GPT-5.4 (balanceado)</option>
              <option value="gpt-5.4:high">GPT-5.4 + Reasoning high (lento, mais preciso)</option>
              <option value="gpt-5.4:xhigh">GPT-5.4 + Reasoning xhigh (muito lento, máximo)</option>
              <option value={modelInput && !['gpt-4.1','gpt-4.1-mini','gpt-5','gpt-5.4','gpt-5.4:high','gpt-5.4:xhigh'].includes(modelInput) ? modelInput : '___custom'}
                style={{ display: modelInput && !['gpt-4.1','gpt-4.1-mini','gpt-5','gpt-5.4','gpt-5.4:high','gpt-5.4:xhigh'].includes(modelInput) ? 'block' : 'none' }}>
                {modelInput} (personalizado)
              </option>
            </select>
            {(modelInput === 'gpt-5.4:high' || modelInput === 'gpt-5.4:xhigh') && (
              <div style={{ marginTop: '0.4rem', fontSize: '0.8rem', color: '#d97706', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                ⚠ Reasoning pode demorar vários minutos por avaliação e tem custo elevado.
              </div>
            )}
          </div>
          {envMsg && (
            <div style={{ marginBottom: '0.75rem', fontSize: '0.875rem', color: envMsg.type === 'ok' ? '#16a34a' : '#dc2626', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              {envMsg.type === 'ok'
                ? <CheckCircle size={14} weight="duotone" />
                : <XCircle size={14} weight="duotone" />}
              {envMsg.text}
            </div>
          )}
          <button type="submit" className="btn-primary" disabled={savingEnv} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <FloppyDisk size={16} weight="duotone" />
            {savingEnv ? 'Salvando...' : 'Salvar configurações'}
          </button>
        </form>
      </div>

      {/* Atualizar Dados */}
      <div className="card">
        <div className="card-title"><ArrowsClockwise size={18} weight="duotone" /> Atualizar Dados</div>
        <p style={{ color: '#6b7280', fontSize: '0.875rem', marginBottom: '1rem' }}>
          Força a re-leitura dos documentos normativos e dos dados públicos da CVM.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <div>
            <button
              className="btn-secondary"
              onClick={handleRefreshChecklist}
              disabled={refreshingChecklist}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
            >
              <ArrowsClockwise size={16} weight="duotone" style={refreshingChecklist ? { animation: 'spin 1s linear infinite' } : {}} />
              {refreshingChecklist ? 'Atualizando...' : 'Atualizar Resolução CVM 80'}
            </button>
            {checklistMsg && (
              <div style={{ marginTop: '0.4rem', fontSize: '0.8rem', color: checklistMsg.type === 'ok' ? '#16a34a' : '#dc2626' }}>
                {checklistMsg.text}
              </div>
            )}
          </div>
          <div>
            <button
              className="btn-secondary"
              onClick={handleRefreshCvm}
              disabled={refreshingCvm}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
            >
              <ArrowsClockwise size={16} weight="duotone" style={refreshingCvm ? { animation: 'spin 1s linear infinite' } : {}} />
              {refreshingCvm ? 'Limpando cache...' : 'Atualizar dados CVM'}
            </button>
            {cvmMsg && (
              <div style={{ marginTop: '0.4rem', fontSize: '0.8rem', color: cvmMsg.type === 'ok' ? '#16a34a' : '#dc2626' }}>
                {cvmMsg.text}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Configurações do App */}
      {appSettings && (
        <div className="card">
          <div className="card-title">Configurações do App</div>
          {[
            ['Versão', appSettings.version],
            ['Modelo OpenAI', appSettings.openai_model],
            ['Embeddings', appSettings.embedding_model],
            ['Cache Máx.', `${appSettings.max_cache_size_gb} GB`],
            ['CNPJ Padrão', appSettings.default_cnpj || '—'],
          ].map(([label, value]) => (
            <div key={label} className="settings-row">
              <span className="settings-label">{label}</span>
              <span className="settings-value">{value}</span>
            </div>
          ))}
        </div>
      )}

      {/* Minha Conta */}
      <div className="card">
        <div className="card-title"><UserCircle size={18} weight="duotone" /> Minha Conta</div>
        <div className="settings-row">
          <span className="settings-label">Nome</span>
          <span className="settings-value">{user?.name || '—'}</span>
        </div>
        <div className="settings-row">
          <span className="settings-label">Email</span>
          <span className="settings-value">{user?.email}</span>
        </div>
      </div>
    </div>
  )
}
