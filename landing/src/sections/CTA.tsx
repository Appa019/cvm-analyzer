import { motion } from 'framer-motion'
import { ArrowRight, GithubLogo, CheckCircle } from '@phosphor-icons/react'
import ScrollReveal from '../components/ScrollReveal'

function ScoreDonut() {
  const radius = 42
  const stroke = 7
  const circumference = 2 * Math.PI * radius
  const progress = 0.87
  const offset = circumference * (1 - progress)

  return (
    <div
      className="rounded-2xl p-6 flex flex-col items-center gap-5"
      style={{
        background: 'rgba(255,255,255,0.04)',
        border: '1px solid rgba(255,255,255,0.08)',
        backdropFilter: 'blur(12px)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      }}
    >
      {/* Donut ring */}
      <div className="relative w-28 h-28">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          {/* Track */}
          <circle
            cx="50" cy="50" r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.07)"
            strokeWidth={stroke}
          />
          {/* Progresso */}
          <circle
            cx="50" cy="50" r={radius}
            fill="none"
            stroke="#33A76B"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        {/* Valor no centro */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="font-display font-bold text-white leading-none"
            style={{ fontSize: '1.625rem', fontVariantNumeric: 'tabular-nums' }}
          >
            87%
          </span>
          <span className="text-[10px] text-white/35 uppercase tracking-wider mt-0.5">score</span>
        </div>
        {/* Glow */}
        <div
          className="absolute inset-0 rounded-full pointer-events-none"
          style={{ boxShadow: '0 0 32px rgba(51,167,107,0.25)' }}
        />
      </div>

      {/* Métricas abaixo */}
      <div className="w-full flex flex-col gap-2">
        {[
          { label: '156 itens', sub: 'Anexo C avaliados' },
          { label: '5 módulos', sub: 'integrados' },
          { label: 'Categoria A', sub: 'classificação' },
        ].map(item => (
          <div
            key={item.label}
            className="flex items-center gap-2.5 px-3 py-2 rounded-xl"
            style={{ background: 'rgba(255,255,255,0.03)' }}
          >
            <CheckCircle size={14} weight="fill" className="text-[#33A76B] flex-shrink-0" />
            <span className="text-white/80 font-medium text-xs">{item.label}</span>
            <span className="text-white/30 text-xs ml-auto">{item.sub}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function CTA() {
  return (
    <section
      className="py-24 lg:py-32 relative overflow-hidden"
      style={{ background: '#0A1F14' }}
    >

      <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <div
            className="rounded-3xl border border-white/10 p-8 sm:p-10 lg:p-14"
            style={{
              background: 'rgba(255,255,255,0.025)',
              backdropFilter: 'blur(8px)',
              boxShadow: '0 0 0 1px rgba(255,255,255,0.04), 0 24px 60px rgba(0,0,0,0.35)',
            }}
          >
            <div className="flex flex-col lg:flex-row items-start lg:items-center gap-10 lg:gap-16">
              {/* Lado esquerdo: texto + CTAs */}
              <div className="flex-1 flex flex-col gap-6">
                <motion.span
                  initial={{ opacity: 0, y: 8 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4 }}
                  className="section-badge-dark w-fit"
                >
                  Comece hoje mesmo
                </motion.span>

                <motion.h2
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: 0.1 }}
                  className="font-display font-bold text-white leading-tight"
                  style={{ fontSize: 'clamp(1.75rem, 4vw, 2.75rem)', letterSpacing: '-0.025em' }}
                >
                  Pronto para automatizar a análise de documentos CVM?
                </motion.h2>

                <motion.p
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: 0.2 }}
                  className="text-base text-white/50 leading-relaxed max-w-lg"
                >
                  Analise FRE, DFP, FCA e IPE com IA — 156 itens normativos do Anexo C,
                  RAG multi-agêntico por empresa e diff semântico entre versões.
                </motion.p>

                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: 0.3 }}
                  className="flex flex-col sm:flex-row gap-3"
                >
                  <a href="/app/login" className="btn-primary text-sm px-7 py-3.5">
                    Acessar Plataforma
                    <ArrowRight size={16} weight="bold" />
                  </a>
                  <a
                    href="https://github.com/Appa019/fre-analyzer"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-outline-light text-sm px-7 py-3.5"
                  >
                    <GithubLogo size={16} weight="duotone" />
                    Ver no GitHub
                  </a>
                </motion.div>

                <motion.p
                  initial={{ opacity: 0 }}
                  whileInView={{ opacity: 1 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: 0.4 }}
                  className="text-xs text-white/25"
                >
                  Código aberto (MIT) · Dados locais · Feito para compliance CVM
                </motion.p>
              </div>

              {/* Lado direito: score widget */}
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, delay: 0.2 }}
                className="flex-shrink-0 w-full sm:w-64"
              >
                <ScoreDonut />
              </motion.div>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  )
}
