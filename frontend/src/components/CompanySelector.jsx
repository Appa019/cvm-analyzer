import { useState, useEffect } from 'react'
import { Buildings } from '@phosphor-icons/react'
import useCompanyStore from '../store/companyStore'
import { useAuth } from '../context/AuthContext'

export default function CompanySelector() {
  const { selectedCompany, setSelectedCompany, clearCompany } = useCompanyStore()
  const { authHeaders } = useAuth()
  const [companies, setCompanies] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadCompanies()
  }, [])

  async function loadCompanies() {
    setLoading(true)
    try {
      const res = await fetch('/api/cvm/status', { headers: authHeaders() })
      if (res.ok) {
        const data = await res.json()
        setCompanies(data.local_companies || [])
      }
    } catch {
      setCompanies([])
    } finally {
      setLoading(false)
    }
  }

  function handleChange(e) {
    const cnpj = e.target.value
    if (!cnpj) {
      clearCompany()
      return
    }
    const company = companies.find(c => c.cnpj === cnpj)
    if (company) setSelectedCompany(company)
  }

  return (
    <div className="company-selector">
      <div className="company-select-wrap">
        <Buildings size={14} weight="duotone" className="company-select-icon" />
        <select
          className="company-select"
          value={selectedCompany?.cnpj || ''}
          onChange={handleChange}
          disabled={loading}
        >
          <option value="">{loading ? 'Carregando...' : 'Selecionar empresa...'}</option>
          {companies.map(c => (
            <option key={c.cnpj} value={c.cnpj}>{c.name}</option>
          ))}
        </select>
      </div>
    </div>
  )
}
