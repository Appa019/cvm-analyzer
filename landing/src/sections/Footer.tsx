import { GithubLogo, ArrowUpRight } from '@phosphor-icons/react'

const navLinks = [
  { label: 'Funcionalidades', href: '#features', external: false },
  { label: 'Como Funciona', href: '#how-it-works', external: false },
  { label: 'Interface', href: '#screenshots', external: false },
  { label: 'Tecnologias', href: '#tech-stack', external: false },
]

export default function Footer() {
  const handleNav = (href: string) => {
    const el = document.querySelector(href)
    if (el) el.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <footer
      style={{ background: '#0A1F14', borderTop: '1px solid rgba(255,255,255,0.06)' }}
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex flex-col sm:flex-row items-start justify-between gap-10">
          {/* Logo + tagline */}
          <div className="flex flex-col gap-3">
            <a
              href="#"
              onClick={e => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }) }}
              className="flex items-center gap-2.5 font-display font-bold text-white/80 hover:text-white transition-colors w-fit group"
            >
              <img
                src="/favicon.svg"
                alt="CVM Analyzer"
                className="h-6 w-auto brightness-0 invert opacity-70 group-hover:opacity-100 transition-opacity"
              />
              <span className="text-sm tracking-tight">CVM Analyzer</span>
            </a>
            <p className="text-xs text-white/25 max-w-xs leading-relaxed">
              Análise de Formulários de Referência com inteligência artificial contra a CVM Resolução 80.
            </p>
            <a
              href="https://github.com/Appa019/cvm-analyzer"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-white/35 hover:text-white/70 transition-colors w-fit mt-1"
            >
              <GithubLogo size={13} weight="duotone" />
              GitHub
              <ArrowUpRight size={11} weight="bold" />
            </a>
          </div>

          {/* Links de navegação */}
          <div className="flex flex-col gap-3">
            <p className="text-[11px] font-semibold text-white/25 uppercase tracking-widest">Navegação</p>
            <nav>
              <ul className="flex flex-col gap-2">
                {navLinks.map(link => (
                  <li key={link.label}>
                    <button
                      onClick={() => handleNav(link.href)}
                      className="text-sm text-white/40 hover:text-white/75 transition-colors text-left"
                    >
                      {link.label}
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
          </div>

          {/* Plataforma */}
          <div className="flex flex-col gap-3">
            <p className="text-[11px] font-semibold text-white/25 uppercase tracking-widest">Plataforma</p>
            <ul className="flex flex-col gap-2">
              {[
                { label: 'Avaliação de FRE', href: '/app/login' },
                { label: 'Comparação (Diff)', href: '/app/login' },
                { label: 'Chat Regulatório', href: '/app/login' },
                { label: 'Arquivo CVM', href: '/app/login' },
              ].map(item => (
                <li key={item.label}>
                  <a
                    href={item.href}
                    className="text-sm text-white/40 hover:text-white/75 transition-colors"
                  >
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Linha inferior */}
        <div
          className="mt-10 pt-6 flex flex-col sm:flex-row items-center justify-between gap-3"
          style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}
        >
          <p className="text-xs text-white/25">
            &copy; 2026 CVM Analyzer. Código aberto (MIT).
          </p>
          <p className="text-xs text-white/20">
            CVM Analyzer · Análise de documentos CVM com IA
          </p>
        </div>
      </div>
    </footer>
  )
}
