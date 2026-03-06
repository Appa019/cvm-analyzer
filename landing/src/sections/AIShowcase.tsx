import { motion } from 'framer-motion'
import { ListChecks, Brain, ChatCircleDots } from '@phosphor-icons/react'
import ScrollReveal from '../components/ScrollReveal'

const capabilities = [
  {
    icon: ListChecks,
    title: 'Análise Normativa',
    description: 'Cada item do Anexo C avaliado individualmente com fundamentação na Resolução 80.',
    accent: '#33A76B',
  },
  {
    icon: Brain,
    title: 'Outputs Estruturados',
    description: 'Structured outputs da OpenAI garantem respostas em formato padronizado e confiável.',
    accent: '#75A5FF',
  },
  {
    icon: ChatCircleDots,
    title: 'RAG Contextual',
    description: 'Chatbot com respostas fundamentadas nos documentos normativos enviados.',
    accent: '#F59E0B',
  },
]

interface TerminalLineProps {
  prefix?: string
  text: string
  delay: number
  dim?: boolean
}

function TerminalLine({ prefix = '$', text, delay, dim = false }: TerminalLineProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.35, delay, ease: 'easeOut' }}
      className="flex gap-2.5 font-mono text-[13px] leading-relaxed"
    >
      <span className="text-[#33A76B] select-none flex-shrink-0">{prefix}</span>
      <span className={dim ? 'text-white/35' : 'text-white/70'}>{text}</span>
    </motion.div>
  )
}

interface ResultLineProps {
  label: string
  score: string
  badge: string
  badgeColor: string
  delay: number
}

function ResultLine({ label, score, badge, badgeColor, delay }: ResultLineProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.35, delay, ease: 'easeOut' }}
      className="flex items-center gap-3 font-mono text-[13px] leading-relaxed"
    >
      <span className="text-white/25 select-none flex-shrink-0">›</span>
      <span className="text-white/55 flex-1 min-w-0 truncate">{label}</span>
      <span className="text-white/75 tabular-nums w-10 text-right flex-shrink-0">{score}</span>
      <span
        className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide flex-shrink-0"
        style={{ backgroundColor: `${badgeColor}1A`, color: badgeColor, border: `1px solid ${badgeColor}30` }}
      >
        {badge}
      </span>
    </motion.div>
  )
}

export default function AIShowcase() {
  return (
    <section className="py-24 lg:py-32 relative overflow-hidden" style={{ background: '#0D1A14' }}>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <ScrollReveal>
          <div className="flex flex-col items-center text-center gap-4 mb-16">
            <span className="section-badge-dark">Inteligência Artificial</span>
            <h2
              className="font-display font-bold text-white leading-tight"
              style={{ fontSize: 'clamp(1.75rem, 4vw, 2.5rem)', letterSpacing: '-0.025em' }}
            >
              Três camadas de IA analisando conformidade.
            </h2>
            <p className="text-lg text-white/45 leading-relaxed max-w-2xl">
              Da análise normativa ao chatbot regulatório — inteligência artificial em cada etapa
              do processo.
            </p>
          </div>
        </ScrollReveal>

        <div className="grid lg:grid-cols-5 gap-8 lg:gap-10 items-start">
          {/* Terminal mockup — 3/5 */}
          <ScrollReveal className="lg:col-span-3">
            <div
              className="rounded-2xl overflow-hidden border border-white/[0.08]"
              style={{
                background: '#0a120d',
                boxShadow: '0 0 0 1px rgba(255,255,255,0.04), 0 24px 60px rgba(0,0,0,0.5), 0 0 40px rgba(0,112,60,0.12)',
              }}
            >
              {/* Barra do terminal */}
              <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.06]" style={{ background: 'rgba(255,255,255,0.025)' }}>
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
                </div>
                <span className="text-[11px] text-white/20 font-mono ml-2 tracking-wide">
                  cvm-analyzer — análise
                </span>
              </div>

              {/* Corpo do terminal */}
              <div className="p-5 lg:p-6 flex flex-col gap-2.5">
                <TerminalLine text="cvm-analyzer evaluate --file FRE_Empresa_2025.pdf" delay={0} />
                <TerminalLine prefix="›" text="Carregando documento... 156 itens a avaliar" delay={0.15} dim />
                <TerminalLine prefix="›" text="Conectando à OpenAI Structured Outputs API..." delay={0.3} dim />

                <div className="h-px my-1" style={{ background: 'rgba(255,255,255,0.05)' }} />

                <ResultLine label="Identificação do emissor" score="95%" badge="Completo" badgeColor="#10B981" delay={0.5} />
                <ResultLine label="Fatores de risco" score="62%" badge="Parcial" badgeColor="#F59E0B" delay={0.62} />
                <ResultLine label="Administradores" score="88%" badge="Completo" badgeColor="#10B981" delay={0.74} />
                <ResultLine label="Remuneração" score="0%" badge="Ausente" badgeColor="#EF4444" delay={0.86} />
                <ResultLine label="Estrutura de capital" score="91%" badge="Completo" badgeColor="#10B981" delay={0.98} />
                <ResultLine label="Política de dividendos" score="12%" badge="Crítico" badgeColor="#EF4444" delay={1.10} />

                <div className="h-px my-1" style={{ background: 'rgba(255,255,255,0.05)' }} />

                <motion.div
                  initial={{ opacity: 0 }}
                  whileInView={{ opacity: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: 1.3, duration: 0.5 }}
                  className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[13px]"
                >
                  <span className="text-[#33A76B] select-none">$</span>
                  <span className="text-[#33A76B] font-bold">Score final: 87%</span>
                  <span className="text-white/25">·</span>
                  <span className="text-white/35">156/156 itens avaliados</span>
                  <span className="text-white/25">·</span>
                  <span
                    className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide"
                    style={{ backgroundColor: 'rgba(51,167,107,0.15)', color: '#33A76B', border: '1px solid rgba(51,167,107,0.25)' }}
                  >
                    Categoria A
                  </span>
                </motion.div>
              </div>
            </div>
          </ScrollReveal>

          {/* Cards de capacidade — 2/5 */}
          <div className="lg:col-span-2 flex flex-col gap-4">
            {capabilities.map((cap, i) => (
              <ScrollReveal key={cap.title} delay={i * 0.15}>
                <div
                  className="rounded-2xl border border-white/[0.07] p-5 group transition-all duration-300 hover:border-white/[0.14] hover:bg-white/[0.04]"
                  style={{ background: 'rgba(255,255,255,0.025)' }}
                >
                  <div className="flex items-start gap-3 mb-3">
                    <div
                      className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5 transition-transform duration-300 group-hover:scale-110"
                      style={{ backgroundColor: `${cap.accent}18` }}
                    >
                      <cap.icon size={18} weight="duotone" style={{ color: cap.accent }} />
                    </div>
                    <div>
                      <h3 className="font-display font-semibold text-white text-sm leading-snug mb-1.5">
                        {cap.title}
                      </h3>
                      <p className="text-sm text-white/40 leading-relaxed">{cap.description}</p>
                    </div>
                  </div>
                  {/* Barra de acento */}
                  <div
                    className="h-[2px] w-12 rounded-full mt-1 opacity-60 group-hover:opacity-100 group-hover:w-20 transition-all duration-300"
                    style={{ backgroundColor: cap.accent }}
                  />
                </div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
