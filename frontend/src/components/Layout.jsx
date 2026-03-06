import { NavLink } from 'react-router-dom'
import { ClipboardText, ArrowsLeftRight, ChatsTeardrop, FolderOpen, GearSix, Buildings, CurrencyDollar } from '@phosphor-icons/react'
import CompanySelector from './CompanySelector'

const navItems = [
  { to: '/init', icon: Buildings, label: 'Empresas' },
  { to: '/', icon: ClipboardText, label: 'Avaliação' },
  { to: '/diff', icon: ArrowsLeftRight, label: 'Comparação' },
  { to: '/chat', icon: ChatsTeardrop, label: 'Chat IA' },
  { to: '/archive', icon: FolderOpen, label: 'Arquivo' },
  { to: '/costs', icon: CurrencyDollar, label: 'Custos' },
]

export default function Layout({ children }) {
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <img src="/images/logo-dark.png" alt="CVM Analyzer" className="sidebar-logo" />
        </div>
        <CompanySelector />

        <nav className="sidebar-nav">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              <Icon size={20} weight="duotone" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <NavLink
            to="/settings"
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            <GearSix size={20} weight="duotone" />
            <span>Configurações</span>
          </NavLink>
        </div>
      </aside>

      <main className="main-content">
        {children}
      </main>
    </div>
  )
}
