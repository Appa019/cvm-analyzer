import { REPO_URL } from '../links'

export function Footer() {
  return (
    <footer className="mx-auto max-w-page px-5 pb-12 pt-20 sm:px-8">
      <p className="display text-[clamp(2.5rem,9vw,7.5rem)]">CVM Analyzer</p>
      <div className="mt-10 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <p className="max-w-[48ch] text-muted">
          Exercício acadêmico sobre dados públicos da CVM. Código sob licença MIT.
        </p>
        <ul className="flex gap-7 font-medium">
          <li><a href={REPO_URL} className="link">Código no GitHub</a></li>
          <li><a href="https://pedropestana.dev" className="link">Pedro Pestana</a></li>
        </ul>
      </div>
    </footer>
  )
}
