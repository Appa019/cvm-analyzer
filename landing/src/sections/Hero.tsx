import { motion } from 'framer-motion'
import { ArrowRight, GithubLogo, Sparkle } from '@phosphor-icons/react'

const stats = [
  { value: '156', label: 'Itens CVM' },
  { value: '4', label: 'Tipos de Doc' },
  { value: 'RAG', label: 'Multi-agêntico' },
]

export default function Hero() {
  return (
    <section
      className="relative min-h-screen flex flex-col items-center pt-32 pb-0 overflow-hidden"
      style={{ background: '#0A1F14' }}
    >
      {/* Grid sutil */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
            backgroundSize: '52px 52px',
          }}
        />
      </div>

      {/* Conteúdo centralizado */}
      <div className="relative z-10 max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col items-center text-center gap-7">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <span className="section-badge-dark">
            <Sparkle size={12} weight="fill" />
            Análise de Documentos CVM com Inteligência Artificial
          </span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.1 }}
          className="font-display font-bold leading-[1.1] tracking-tight"
          style={{ fontSize: 'clamp(2.4rem, 6vw, 4.25rem)', letterSpacing: '-0.025em' }}
        >
          <span className="text-white">Analise documentos CVM com </span>
          <span className="text-[#33A76B]">inteligência artificial.</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.2 }}
          className="text-lg text-white/55 leading-relaxed max-w-2xl"
        >
          Analise, compare e converse sobre FRE, DFP, FCA e IPE — avaliação automática de
          156 itens do Anexo C, diff semântico e RAG multi-agêntico por empresa.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.65, delay: 0.3 }}
          className="flex flex-wrap justify-center gap-3"
        >
          <a href="/app/login" className="btn-primary">
            Começar Agora
            <ArrowRight size={16} weight="bold" />
          </a>
          <a
            href="https://github.com/Appa019/fre-analyzer"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-outline-light"
          >
            <GithubLogo size={16} weight="duotone" />
            Ver no GitHub
          </a>
        </motion.div>

        {/* Stats */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.45 }}
          className="flex items-center gap-8 pt-2"
        >
          {stats.map((stat, i) => (
            <div key={i} className="flex flex-col items-center gap-0.5">
              <span
                className="font-display font-bold text-2xl text-white"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {stat.value}
              </span>
              <span className="text-xs text-white/35 uppercase tracking-wider">{stat.label}</span>
            </div>
          ))}
        </motion.div>
      </div>

      {/* Browser mockup com perspectiva */}
      <motion.div
        initial={{ opacity: 0, y: 56, scale: 0.94 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.9, delay: 0.55, ease: [0.16, 1, 0.3, 1] }}
        className="relative z-10 w-full max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 mt-14"
        style={{ perspective: '1400px' }}
      >
        <div
          className="rounded-xl overflow-hidden border border-white/[0.12]"
          style={{
            transform: 'rotateX(4deg) scale(1.01)',
            transformOrigin: 'center top',
            boxShadow:
              '0 0 0 1px rgba(255,255,255,0.04), 0 32px 80px rgba(0,0,0,0.6)',
          }}
        >
          {/* Barra do browser */}
          <div className="flex items-center gap-2 px-4 py-2.5 bg-[#161f18] border-b border-white/[0.06]">
            <div className="flex gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
              <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
              <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
            </div>
            <div className="flex-1 mx-8">
              <div className="bg-white/[0.06] rounded-md px-3 py-1 text-[11px] text-white/25 font-mono text-center">
                localhost:5173/evaluation
              </div>
            </div>
          </div>
          {/* Screenshot */}
          <img
            src="/screenshots/evaluation.png"
            alt="CVM Analyzer — Tela de avaliação"
            className="w-full block"
            loading="eager"
          />
        </div>

        {/* Fade sólido na borda inferior */}
        <div
          className="absolute bottom-0 left-0 right-0 h-48 pointer-events-none"
          style={{ background: '#0A1F14' }}
        />
      </motion.div>
    </section>
  )
}
