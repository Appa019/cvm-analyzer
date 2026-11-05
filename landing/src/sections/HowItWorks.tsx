const STEPS = [
  {
    title: 'Baixa os documentos da CVM',
    text: 'Você busca a companhia pelo nome nos dados abertos da CVM. O app baixa os PDFs do ENET com Playwright, fica só com a versão mais recente de cada documento e mostra o progresso enquanto baixa.',
    img: { src: '/screenshots/download.webp', w: 1160, h: 770, alt: 'Download em andamento dos comunicados (IPE) da WEG S.A.: 42%, 34 de 81 documentos, com a lista dos já baixados.' },
  },
  {
    title: 'Confere contra o Anexo C',
    text: 'Os 156 itens vão para a Responses API da OpenAI, até 15 por vez. O resultado sai por seção como completo, parcial ou ausente, considera até cinco versões anteriores do mesmo documento e pode ser exportado em PDF ou Excel.',
    img: { src: '/screenshots/avaliacao.webp', w: 1515, h: 710, alt: 'Tela Avaliação com o Formulário de Referência 2025 da WEG S.A. selecionado no arquivo local.' },
  },
  {
    title: 'Compara duas versões',
    text: 'Escolha dois documentos, do arquivo local ou enviados em PDF. O diff mostra por seção o que entrou, saiu ou mudou, e o modelo resume o impacto regulatório e de negócio.',
    img: { src: '/screenshots/comparacao.webp', w: 2030, h: 920, alt: 'Resultado da comparação entre os Formulários de Referência 2024 e 2025 da WEG S.A.: 92 seções comparadas, 4 adicionadas, 4 removidas e 82 modificadas.' },
  },
]

export function HowItWorks() {
  return (
    <section id="como-funciona" className="mx-auto max-w-page px-5 py-28 sm:px-8 md:py-36">
      <h2 className="display text-[clamp(2rem,4.5vw,3.5rem)]">Como funciona</h2>

      <div className="mt-16 space-y-24 md:space-y-32">
        {STEPS.map((s) => (
          <article key={s.title} className="grid gap-8 lg:grid-cols-12 lg:gap-10">
            <div className="lg:col-span-5">
              <h3 className="text-balance text-2xl font-bold leading-tight md:text-[28px]">{s.title}</h3>
              <p className="mt-4 max-w-[60ch]">{s.text}</p>
            </div>
            <figure className="lg:col-span-7" data-ui>
              <img src={s.img.src} width={s.img.w} height={s.img.h} alt={s.img.alt} className="shot" loading="lazy" />
            </figure>
          </article>
        ))}
      </div>

      <div className="mt-24 grid gap-12 md:mt-32 md:grid-cols-2 md:gap-10">
        <div>
          <h3 className="text-2xl font-bold leading-tight md:text-[28px]">Responde perguntas sobre os PDFs</h3>
          <p className="mt-4 max-w-[60ch]">
            Cada empresa ganha um Vector Store próprio na OpenAI, separado por CNPJ. O chat busca
            nos documentos baixados e responde citando a fonte e a data do documento.
          </p>
        </div>
        <div>
          <h3 className="text-2xl font-bold leading-tight md:text-[28px]">Mostra quanto custou</h3>
          <p className="mt-4 max-w-[60ch]">
            Uma tela soma os tokens e o custo estimado de cada chamada, por modelo, empresa e mês,
            para você saber o preço de uma avaliação antes de rodar a próxima.
          </p>
        </div>
      </div>
    </section>
  )
}
