import { Upload, Brain, ListChecks, Export } from '@phosphor-icons/react'
import ScrollReveal from '../components/ScrollReveal'
import type { Icon } from '@phosphor-icons/react'

interface Step {
  number: string
  title: string
  description: string
  icon: Icon
}

const steps: Step[] = [
  {
    number: '01',
    title: 'Envie o FRE',
    description:
      'Upload do documento em PDF ou cole a URL pública do Formulário de Referência direto da CVM.',
    icon: Upload,
  },
  {
    number: '02',
    title: 'IA Analisa',
    description:
      '156 itens do Anexo C avaliados automaticamente contra a CVM Resolução 80 com structured outputs.',
    icon: Brain,
  },
  {
    number: '03',
    title: 'Revise Resultados',
    description:
      'Score por item com status (Completo, Parcial, Ausente, Crítico) e recomendações de melhoria.',
    icon: ListChecks,
  },
  {
    number: '04',
    title: 'Exporte e Compare',
    description:
      'Gere relatórios em PDF e Excel. Compare versões com diff semântico para acompanhar evolução.',
    icon: Export,
  },
]

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="py-24 lg:py-32" style={{ background: '#F0FAF5' }}>
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <div className="flex flex-col items-center text-center gap-4 mb-20">
            <span className="section-badge">Como Funciona</span>
            <h2
              className="font-display font-bold text-[#0f1a12] leading-tight"
              style={{ fontSize: 'clamp(1.75rem, 4vw, 2.5rem)', letterSpacing: '-0.025em' }}
            >
              4 passos para avaliar seu FRE.
            </h2>
            <p className="text-lg text-[#4A6456] leading-relaxed max-w-2xl">
              Do upload ao relatório completo — rápido, preciso e fundamentado na regulamentação vigente.
            </p>
          </div>
        </ScrollReveal>

        {/* Timeline vertical alternada */}
        <div className="relative">
          {/* Linha central — desktop */}
          <div
            className="hidden lg:block absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-px"
            style={{ background: '#99D3B5' }}
            aria-hidden="true"
          />
          {/* Linha lateral — mobile */}
          <div
            className="lg:hidden absolute top-0 bottom-0 left-5 w-px"
            style={{ background: '#99D3B5' }}
            aria-hidden="true"
          />

          <div className="flex flex-col gap-0">
            {steps.map((step, i) => {
              const isLeft = i % 2 === 0
              const IconComp = step.icon

              return (
                <ScrollReveal key={step.number} delay={i * 0.12}>
                  <div className="relative flex items-center py-8 lg:py-10">
                    {/* Mobile layout — sempre à direita da linha */}
                    <div className="lg:hidden flex items-start gap-5 pl-14 w-full">
                      {/* Círculo numerado mobile */}
                      <div
                        className="absolute left-0 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-[#00703C] flex items-center justify-center shadow-md z-10"
                        style={{ boxShadow: '0 0 0 4px #F0FAF5, 0 4px 16px rgba(0,112,60,0.3)' }}
                      >
                        <span className="text-white font-display font-bold text-xs">{step.number}</span>
                      </div>

                      <div className="bg-white rounded-2xl border border-[#CCE9DA] p-5 flex-1"
                        style={{ boxShadow: '0 2px 12px rgba(0,112,60,0.08)' }}>
                        <div className="flex items-center gap-3 mb-2">
                          <div className="w-9 h-9 rounded-xl bg-[#E6F5ED] flex items-center justify-center flex-shrink-0">
                            <IconComp size={18} weight="duotone" className="text-[#00703C]" />
                          </div>
                          <h3 className="font-display font-semibold text-[#0f1a12] text-base">{step.title}</h3>
                        </div>
                        <p className="text-sm text-[#4A6456] leading-relaxed pl-12">{step.description}</p>
                      </div>
                    </div>

                    {/* Desktop layout — alternado */}
                    <div className="hidden lg:grid lg:grid-cols-2 lg:gap-0 w-full items-center">
                      {/* Lado esquerdo */}
                      <div className={`${isLeft ? 'flex justify-end pr-14' : ''}`}>
                        {isLeft && (
                          <div
                            className="bg-white rounded-2xl border border-[#CCE9DA] p-6 max-w-sm w-full"
                            style={{ boxShadow: '0 2px 16px rgba(0,112,60,0.08)' }}
                          >
                            <div className="flex items-center gap-3 mb-3">
                              <div className="w-10 h-10 rounded-xl bg-[#E6F5ED] flex items-center justify-center flex-shrink-0">
                                <IconComp size={20} weight="duotone" className="text-[#00703C]" />
                              </div>
                              <h3 className="font-display font-semibold text-[#0f1a12] text-base">{step.title}</h3>
                            </div>
                            <p className="text-sm text-[#4A6456] leading-relaxed">{step.description}</p>
                          </div>
                        )}
                      </div>

                      {/* Círculo central */}
                      <div
                        className="absolute left-1/2 -translate-x-1/2 w-12 h-12 rounded-full bg-[#00703C] flex items-center justify-center z-10"
                        style={{ boxShadow: '0 0 0 5px #F0FAF5, 0 4px 20px rgba(0,112,60,0.35)' }}
                      >
                        <span className="text-white font-display font-bold text-sm">{step.number}</span>
                      </div>

                      {/* Lado direito */}
                      <div className={`${!isLeft ? 'flex justify-start pl-14' : ''}`}>
                        {!isLeft && (
                          <div
                            className="bg-white rounded-2xl border border-[#CCE9DA] p-6 max-w-sm w-full"
                            style={{ boxShadow: '0 2px 16px rgba(0,112,60,0.08)' }}
                          >
                            <div className="flex items-center gap-3 mb-3">
                              <div className="w-10 h-10 rounded-xl bg-[#E6F5ED] flex items-center justify-center flex-shrink-0">
                                <IconComp size={20} weight="duotone" className="text-[#00703C]" />
                              </div>
                              <h3 className="font-display font-semibold text-[#0f1a12] text-base">{step.title}</h3>
                            </div>
                            <p className="text-sm text-[#4A6456] leading-relaxed">{step.description}</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </ScrollReveal>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}
