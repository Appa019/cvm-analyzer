import { REPO_URL } from '../links'

export function Hero() {
  return (
    <section id="topo" className="mx-auto max-w-page px-5 pb-28 pt-14 sm:px-8 md:pt-20">
      <h1 className="display enter text-[clamp(2.5rem,7vw,5.5rem)]">
        Documentos CVM, <br className="hidden md:inline" />
        item a item
      </h1>
      <div className="enter-late mt-8 grid gap-8 md:grid-cols-12 md:items-end">
        <p className="max-w-[60ch] text-lg md:col-span-7 md:text-xl">
          Ferramenta local e de código aberto que baixa FRE, DFP, FCA e IPE de uma companhia
          aberta direto da CVM e confere o Formulário de Referência contra os 156 itens do Anexo C
          da Resolução CVM 80.
        </p>
        <div className="flex flex-wrap items-center gap-x-7 gap-y-4 md:col-span-5 md:justify-end">
          <a href={REPO_URL} className="btn">
            Ver o código no GitHub
          </a>
          <a href={`${REPO_URL}#instalação-e-execução`} className="link font-medium">
            Como instalar
          </a>
        </div>
      </div>
      <figure className="mt-14 md:mt-16" data-ui>
        <img
          src="/screenshots/arquivo.webp"
          width={2560}
          height={1600}
          alt="Tela Arquivo do CVM Analyzer: lista de documentos baixados da WEG S.A. e o Formulário de Referência aberto ao lado."
          className="shot"
          fetchPriority="high"
        />
        <figcaption className="mt-3 text-[15px] text-muted">
          Tela Arquivo com documentos públicos da WEG S.A. baixados da CVM.
        </figcaption>
      </figure>
    </section>
  )
}
