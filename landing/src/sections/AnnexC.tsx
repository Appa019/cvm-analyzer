// Generated from resol080consolid.docx with backend/services/checklist_parser.py (21 sections, 135 items).
import sections from '../data/anexo-c.json'

const total = sections.reduce((n, s) => n + 1 + s.itens.length, 0)
const optional = sections.reduce((n, s) => n + s.itens.filter((i) => i.facultativo).length, 0)

export function AnnexC() {
  return (
    <section id="anexo-c" className="mx-auto max-w-page px-5 py-28 sm:px-8 md:py-36">
      <div className="grid gap-12 md:grid-cols-12 md:gap-10">
        <div className="md:col-span-5">
          <div className="md:sticky md:top-10">
            <h2 className="display text-[clamp(2rem,4.5vw,3.5rem)]">O que é conferido</h2>
            <p className="mt-6 max-w-[48ch] text-lg">
              O checklist sai do texto consolidado da Resolução CVM 80 que está no repositório:{' '}
              {sections.length} seções e {total} itens do Anexo C, o conteúdo do Formulário de
              Referência. {optional} deles são facultativos para emissores da Categoria B, e o app
              os avalia à parte.
            </p>
            <p className="mt-4 text-muted">Abra uma seção para ver os itens.</p>
          </div>
        </div>

        <div className="md:col-span-7">
          {sections.map((s) => (
            <details key={s.id} className="group">
              <summary className="flex cursor-pointer list-none items-baseline gap-4 py-3 hover:text-accent [&::-webkit-details-marker]:hidden">
                <span className="w-7 shrink-0 font-semibold tabular-nums">{s.id}</span>
                <span className="flex-1 text-lg font-semibold leading-snug">{s.titulo}</span>
                <span className="shrink-0 text-[15px] text-muted">
                  {s.itens.length} {s.itens.length === 1 ? 'item' : 'itens'}
                </span>
                <span aria-hidden="true" className="w-4 shrink-0 text-center text-xl leading-none transition-transform duration-150 group-open:rotate-45 motion-reduce:transition-none">
                  +
                </span>
              </summary>
              <ul className="space-y-3 pb-6 pl-11">
                {s.itens.map((i) => (
                  <li key={i.id} className="flex gap-3 leading-snug">
                    <span className="w-10 shrink-0 tabular-nums text-muted">{i.id}</span>
                    <span>
                      {i.titulo}
                      {i.facultativo && <span className="text-muted"> (facultativo na Categoria B)</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}
