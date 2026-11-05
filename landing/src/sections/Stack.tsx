const LAYERS = [
  { name: 'Backend', items: 'FastAPI, SQLAlchemy 2.0 assíncrono e SQLite' },
  { name: 'Interface', items: 'React 18, Vite, Tailwind CSS v4, Zustand e TanStack Query' },
  { name: 'Modelo', items: 'OpenAI Responses API, Vector Stores e File Search' },
  { name: 'Documentos', items: 'PyMuPDF e pdfplumber nos PDFs, python-docx no checklist, Playwright no ENET' },
]

export function Stack() {
  return (
    <section id="stack" className="mx-auto max-w-page px-5 py-28 sm:px-8 md:py-36">
      <div className="grid gap-12 md:grid-cols-12 md:gap-10">
        <h2 className="display text-[clamp(2rem,4.5vw,3.5rem)] md:col-span-5">Como é feito</h2>
        <div className="md:col-span-7">
          <dl className="space-y-6">
            {LAYERS.map((l) => (
              <div key={l.name} className="grid gap-1 sm:grid-cols-[9rem_1fr] sm:gap-6">
                <dt className="font-semibold">{l.name}</dt>
                <dd>{l.items}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-12 max-w-[60ch] text-lg">
            Roda na sua máquina, sem login. Banco, cache e PDFs ficam em{' '}
            <code className="text-base">~/.local/share/FREAnalyzer</code>; a única chamada externa,
            além da CVM, é para a OpenAI.
          </p>
        </div>
      </div>
    </section>
  )
}
