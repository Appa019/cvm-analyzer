import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import {
  CurrencyDollar, ArrowsClockwise, Info, ChartBar,
} from '@phosphor-icons/react'

// Formata número de tokens (ex: 1.234.567)
function fmtTokens(n) {
  if (!n) return '0'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

// Formata USD (ex: $0.001234)
function fmtUsd(n) {
  if (!n) return '$0.00'
  if (n < 0.01) return `$${n.toFixed(6)}`
  if (n < 1) return `$${n.toFixed(4)}`
  return `$${n.toFixed(2)}`
}

export default function CostsPage() {
  const { authHeaders } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('empresa') // 'empresa' | 'modelo' | 'mes' | 'precos'

  useEffect(() => { fetchCosts() }, [])

  async function fetchCosts() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/settings/costs', { headers: authHeaders() })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        <ArrowsClockwise size={28} weight="duotone" className="spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#dc2626', fontSize: '0.9rem' }}>
        Erro ao carregar dados de custos: {error}
      </div>
    )
  }

  const s = data?.summary || {}
  const hasData = (s.total_tokens || 0) > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{
        padding: '16px 24px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CurrencyDollar size={20} weight="duotone" style={{ color: 'var(--primary)' }} />
          <span style={{ fontWeight: 600, fontSize: '1rem' }}>Custos</span>
        </div>
        <button
          className="btn-secondary"
          onClick={fetchCosts}
          style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem' }}
        >
          <ArrowsClockwise size={15} weight="duotone" />
          Atualizar
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>

        {/* Aviso split exato vs estimativa */}
        {!s.has_exact_split && hasData && (
          <div style={{
            display: 'flex', alignItems: 'flex-start', gap: '8px', marginBottom: '20px',
            padding: '10px 14px', borderRadius: '8px',
            background: '#fffbeb', border: '1px solid #fde68a', fontSize: '0.82rem', color: '#92400e',
          }}>
            <Info size={16} weight="duotone" style={{ flexShrink: 0, marginTop: '1px' }} />
            <span>
              Registros anteriores armazenam apenas o total de tokens. O custo é uma <strong>estimativa</strong> usando proporção 75% input / 25% output.
              Avaliações futuras terão custo exato (tokens de entrada e saída separados).
            </span>
          </div>
        )}

        {/* Cards de resumo */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px', marginBottom: '28px' }}>
          <SummaryCard
            label="Custo Total"
            value={fmtUsd(s.total_cost_usd)}
            sub={s.has_exact_split ? 'cálculo exato' : 'estimativa'}
            highlight
          />
          <SummaryCard label="Tokens Totais" value={fmtTokens(s.total_tokens)} sub="input + output" />
          <SummaryCard label="Tokens Input"  value={fmtTokens(s.input_tokens)}  sub="prompt / contexto" />
          <SummaryCard label="Tokens Output" value={fmtTokens(s.output_tokens)} sub="resposta gerada" />
        </div>

        {!hasData && (
          <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            <ChartBar size={40} weight="duotone" style={{ opacity: 0.2, display: 'block', margin: '0 auto 12px' }} />
            Nenhuma avaliação realizada ainda.<br />
            Os dados de custo aparecerão após a primeira avaliação.
          </div>
        )}

        {hasData && (
          <>
            {/* Tabs */}
            <div style={{ display: 'flex', gap: '4px', marginBottom: '20px', borderBottom: '1px solid var(--border)', paddingBottom: '0' }}>
              {[
                { key: 'empresa', label: 'Por Empresa' },
                { key: 'modelo', label: 'Por Modelo' },
                { key: 'mes', label: 'Por Mês' },
                { key: 'precos', label: 'Tabela de Preços' },
              ].map(t => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  style={{
                    padding: '7px 14px', fontSize: '0.83rem', fontWeight: tab === t.key ? 600 : 400,
                    background: 'none', border: 'none', cursor: 'pointer',
                    borderBottom: tab === t.key ? '2px solid var(--primary)' : '2px solid transparent',
                    color: tab === t.key ? 'var(--primary)' : 'var(--text-muted)',
                    marginBottom: '-1px', transition: 'color 0.15s',
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {tab === 'empresa' && <TableEmpresa rows={data.by_company} />}
            {tab === 'modelo'  && <TableModelo  rows={data.by_model} />}
            {tab === 'mes'     && <TableMes     rows={data.by_month} />}
            {tab === 'precos'  && <TabelaPrecos pricing={data.pricing} />}
          </>
        )}
      </div>
    </div>
  )
}

function SummaryCard({ label, value, sub, highlight }) {
  return (
    <div style={{
      padding: '16px 18px', borderRadius: '10px',
      background: highlight ? 'var(--primary)' : 'var(--surface)',
      border: `1px solid ${highlight ? 'var(--primary)' : 'var(--border)'}`,
    }}>
      <div style={{ fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: highlight ? 'rgba(255,255,255,0.8)' : 'var(--text-muted)', marginBottom: '6px' }}>
        {label}
      </div>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, color: highlight ? '#fff' : 'var(--text)', fontFamily: 'monospace', letterSpacing: '-0.02em' }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: '0.72rem', color: highlight ? 'rgba(255,255,255,0.65)' : 'var(--text-muted)', marginTop: '4px' }}>
          {sub}
        </div>
      )}
    </div>
  )
}

function TableEmpresa({ rows }) {
  if (!rows?.length) return <Empty />
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={tableStyle}>
        <thead>
          <tr>
            {['CNPJ', 'Avaliações', 'Input', 'Output', 'Total', 'Custo'].map(h => (
              <th key={h} style={thStyle}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.cnpj} style={{ background: i % 2 === 0 ? 'transparent' : 'var(--surface)' }}>
              <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: '0.82rem', fontWeight: 500 }}>{r.cnpj}</td>
              <td style={{ ...tdStyle, textAlign: 'right' }}>{r.eval_count}</td>
              <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }}>{fmtTokens(r.input_tokens)}</td>
              <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }}>{fmtTokens(r.output_tokens)}</td>
              <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }}>{fmtTokens(r.total_tokens)}</td>
              <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', fontWeight: 600, color: 'var(--primary)' }}>{fmtUsd(r.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TableModelo({ rows }) {
  if (!rows?.length) return <Empty />
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={tableStyle}>
        <thead>
          <tr>
            {['Modelo', 'Itens', 'Input', 'Output', 'Total', 'Custo'].map(h => (
              <th key={h} style={thStyle}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.model} style={{ background: i % 2 === 0 ? 'transparent' : 'var(--surface)' }}>
              <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 500 }}>{r.model}</td>
              <td style={{ ...tdStyle, textAlign: 'right' }}>{r.item_count}</td>
              <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }}>{fmtTokens(r.input_tokens)}</td>
              <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }}>{fmtTokens(r.output_tokens)}</td>
              <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }}>{fmtTokens(r.total_tokens)}</td>
              <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace', fontWeight: 600, color: 'var(--primary)' }}>{fmtUsd(r.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TableMes({ rows }) {
  if (!rows?.length) return <Empty />
  const maxCost = Math.max(...rows.map(r => r.cost_usd || 0), 0.000001)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {rows.map(r => {
        const pct = Math.max(4, Math.round((r.cost_usd / maxCost) * 100))
        return (
          <div key={r.month} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ width: '72px', fontSize: '0.82rem', fontFamily: 'monospace', color: 'var(--text-muted)', flexShrink: 0 }}>
              {r.month}
            </div>
            <div style={{ flex: 1, height: '26px', background: 'var(--border)', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{
                height: '100%', width: `${pct}%`,
                background: 'var(--primary)', borderRadius: '4px',
                display: 'flex', alignItems: 'center', paddingLeft: '8px',
                transition: 'width 0.4s ease',
              }}>
                {pct > 20 && (
                  <span style={{ fontSize: '0.72rem', color: '#fff', fontWeight: 600 }}>{fmtTokens(r.total_tokens)}</span>
                )}
              </div>
            </div>
            <div style={{ width: '80px', textAlign: 'right', fontFamily: 'monospace', fontWeight: 600, color: 'var(--primary)', fontSize: '0.88rem' }}>
              {fmtUsd(r.cost_usd)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function TabelaPrecos({ pricing }) {
  const entries = Object.entries(pricing || {}).sort((a, b) => a[1].input_per_1m - b[1].input_per_1m)
  return (
    <div>
      <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '14px' }}>
        Preços por 1 milhão de tokens — fonte: platform.openai.com/docs/models (março 2026)
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              {['Modelo', 'Input / 1M', 'Output / 1M'].map(h => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map(([model, p], i) => (
              <tr key={model} style={{ background: i % 2 === 0 ? 'transparent' : 'var(--surface)' }}>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontWeight: 500 }}>{model}</td>
                <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }}>${p.input_per_1m.toFixed(3)}</td>
                <td style={{ ...tdStyle, textAlign: 'right', fontFamily: 'monospace' }}>${p.output_per_1m.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Empty() {
  return (
    <div style={{ textAlign: 'center', padding: '30px 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
      Nenhum dado disponível.
    </div>
  )
}

const tableStyle = {
  width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem',
}
const thStyle = {
  padding: '8px 12px', textAlign: 'left', fontWeight: 600,
  fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.04em',
  color: 'var(--text-muted)', borderBottom: '1px solid var(--border)',
}
const tdStyle = {
  padding: '9px 12px', borderBottom: '1px solid var(--border)', color: 'var(--text)',
}
