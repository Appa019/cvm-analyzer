import { REPO_URL } from '../links'

const LINKS = [
  { href: '#como-funciona', label: 'Como funciona' },
  { href: '#anexo-c', label: 'Anexo C' },
  { href: '#stack', label: 'Stack' },
]

export function Header() {
  return (
    <header className="mx-auto flex max-w-page items-center justify-between gap-6 px-5 py-5 sm:px-8">
      <a href="#topo" className="text-lg font-extrabold tracking-[-0.01em]">
        CVM Analyzer
      </a>
      <nav aria-label="Seções" className="flex items-center gap-7">
        <ul className="hidden gap-7 md:flex">
          {LINKS.map((l) => (
            <li key={l.href}>
              <a href={l.href} className="hover:text-accent">
                {l.label}
              </a>
            </li>
          ))}
        </ul>
        <a href={REPO_URL} className="btn px-4 py-2 text-[15px]">
          GitHub
        </a>
      </nav>
    </header>
  )
}
