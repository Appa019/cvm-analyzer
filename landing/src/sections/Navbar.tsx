import { useState, useEffect } from 'react'
import { List, X } from '@phosphor-icons/react'

const links = [
  { label: 'Funcionalidades', href: '#features' },
  { label: 'Como Funciona', href: '#how-it-works' },
  { label: 'Interface', href: '#screenshots' },
  { label: 'Tecnologia', href: '#tech-stack' },
]

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const handleNav = (href: string) => {
    setMobileOpen(false)
    const el = document.querySelector(href)
    if (el) el.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex justify-center pt-4 px-4">
      <nav
        className="flex items-center justify-between w-full max-w-[720px] h-12 px-4 rounded-full transition-all duration-300"
        style={
          scrolled
            ? {
                background: 'rgba(10,31,20,0.85)',
                backdropFilter: 'blur(20px)',
                WebkitBackdropFilter: 'blur(20px)',
                border: '1px solid rgba(255,255,255,0.1)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.04)',
              }
            : {
                background: 'rgba(10,31,20,0.4)',
                backdropFilter: 'blur(8px)',
                WebkitBackdropFilter: 'blur(8px)',
                border: '1px solid rgba(255,255,255,0.07)',
              }
        }
      >
        {/* Logo */}
        <a
          href="#"
          onClick={e => {
            e.preventDefault()
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}
          className="flex items-center gap-2 font-display font-bold text-sm text-white/90 hover:text-white transition-colors"
        >
          <img
            src="/favicon.svg"
            alt="CVM Analyzer"
            className="h-5 w-auto brightness-0 invert opacity-90"
          />
          <span className="hidden sm:inline tracking-tight">CVM Analyzer</span>
        </a>

        {/* Links desktop */}
        <ul className="hidden md:flex items-center gap-0.5">
          {links.map(link => (
            <li key={link.href}>
              <button
                onClick={() => handleNav(link.href)}
                className="px-3 py-1.5 rounded-full text-xs font-medium text-white/55 hover:text-white hover:bg-white/[0.08] transition-all duration-200"
              >
                {link.label}
              </button>
            </li>
          ))}
        </ul>

        {/* CTA desktop */}
        <a
          href="/app/login"
          className="hidden md:inline-flex items-center px-4 py-1.5 rounded-full text-xs font-semibold text-[#0A1F14] bg-white hover:bg-white/90 transition-all duration-200"
          style={{ boxShadow: '0 2px 8px rgba(255,255,255,0.15)' }}
        >
          Acessar
        </a>

        {/* Botão mobile */}
        <button
          onClick={() => setMobileOpen(v => !v)}
          className="md:hidden p-1.5 rounded-full text-white/60 hover:text-white hover:bg-white/10 transition-colors"
          aria-label={mobileOpen ? 'Fechar menu' : 'Abrir menu'}
        >
          {mobileOpen ? <X size={18} weight="bold" /> : <List size={18} weight="bold" />}
        </button>
      </nav>

      {/* Menu mobile */}
      {mobileOpen && (
        <div
          className="fixed inset-0 top-16 z-40 md:hidden flex flex-col px-6 py-8 gap-2"
          style={{
            background: 'rgba(10,31,20,0.97)',
            backdropFilter: 'blur(24px)',
          }}
        >
          {links.map(link => (
            <button
              key={link.href}
              onClick={() => handleNav(link.href)}
              className="text-left px-4 py-3 rounded-xl text-base font-medium text-white/70 hover:text-white hover:bg-white/[0.06] transition-colors"
            >
              {link.label}
            </button>
          ))}
          <div className="mt-4 pt-4 border-t border-white/10">
            <a href="/app/login" className="btn-primary w-full justify-center">
              Acessar Plataforma
            </a>
          </div>
        </div>
      )}
    </header>
  )
}
