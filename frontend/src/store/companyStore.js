import { create } from 'zustand'

const STORAGE_KEY = 'cvm_analyzer_company'

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

const useCompanyStore = create((set) => ({
  selectedCompany: loadFromStorage(),

  setSelectedCompany: (company) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(company))
    } catch { /* ignore */ }
    set({ selectedCompany: company })
  },

  clearCompany: () => {
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch { /* ignore */ }
    set({ selectedCompany: null })
  },
}))

export default useCompanyStore
