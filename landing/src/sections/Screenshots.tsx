import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ScrollReveal from '../components/ScrollReveal'

interface ScreenshotTab {
  id: string
  file: string
  label: string
  url: string
  description: string
}

const tabs: ScreenshotTab[] = [
  {
    id: 'evaluation',
    file: 'evaluation.png',
    label: 'Avaliação',
    url: 'localhost:5173/evaluation',
    description:
      'Avalie FRE, DFP, FCA ou IPE contra 156 itens do Anexo C. Score ring por seção, status por item e exportação PDF/Excel.',
  },
  {
    id: 'diff',
    file: 'diff.png',
    label: 'Comparação',
    url: 'localhost:5173/diff',
    description:
      'Comparação semântica entre versões de qualquer documento CVM com análise de impacto gerada por IA.',
  },
  {
    id: 'chat',
    file: 'chat.png',
    label: 'Chat IA',
    url: 'localhost:5173/chat',
    description:
      'RAG multi-agêntico fundamentado em todos os documentos da empresa (FRE, DFP, FCA, IPE) via Vector Store OpenAI.',
  },
  {
    id: 'archive',
    file: 'archive.png',
    label: 'Arquivo',
    url: 'localhost:5173/archive',
    description: 'Documentos baixados localmente: FRE, DFP, FCA e IPE de qualquer companhia aberta. Visualização inline de PDF.',
  },
  {
    id: 'login',
    file: 'login.png',
    label: 'Inicialização',
    url: 'localhost:5173/init',
    description:
      'Busque a empresa pelos dados abertos CVM e baixe todos os documentos disponíveis com progresso em tempo real.',
  },
  {
    id: 'settings',
    file: 'settings.png',
    label: 'Config',
    url: 'localhost:5173/settings',
    description: 'Configure API key OpenAI, modelo, cache e monitore custos por empresa e modelo.',
  },
]

export default function Screenshots() {
  const [active, setActive] = useState(0)
  const current = tabs[active]

  return (
    <section id="screenshots" className="py-24 lg:py-32" style={{ background: '#f8faf9' }}>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <div className="flex flex-col items-center text-center gap-4 mb-12">
            <span className="section-badge">Interface</span>
            <h2
              className="font-display font-bold text-[#0f1a12] leading-tight"
              style={{ fontSize: 'clamp(1.75rem, 4vw, 2.5rem)', letterSpacing: '-0.025em' }}
            >
              Design pensado para compliance.
            </h2>
            <p className="text-lg text-[#4A6456] leading-relaxed max-w-2xl">
              Navegação intuitiva, scores visuais e informações claras para análise regulatória eficiente.
            </p>
          </div>
        </ScrollReveal>

        {/* Pills de navegação */}
        <ScrollReveal>
          <div className="flex justify-center mb-8">
            <div
              className="flex items-center gap-1.5 p-1.5 rounded-full overflow-x-auto no-scrollbar"
              style={{ background: '#E6F5ED', border: '1px solid #CCE9DA' }}
            >
              {tabs.map((tab, i) => (
                <button
                  key={tab.id}
                  onClick={() => setActive(i)}
                  className="relative px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00703C]"
                  style={
                    i === active
                      ? {
                          background: '#00703C',
                          color: '#ffffff',
                          boxShadow: '0 2px 8px rgba(0,112,60,0.35)',
                        }
                      : {
                          color: '#4A6456',
                          background: 'transparent',
                        }
                  }
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
        </ScrollReveal>

        {/* Browser chrome + screenshot */}
        <ScrollReveal>
          <div
            className="rounded-2xl overflow-hidden border border-[#D4E8DC]"
            style={{ boxShadow: '0 4px 24px rgba(0,112,60,0.10), 0 1px 4px rgba(0,0,0,0.06)' }}
          >
            {/* Barra do browser */}
            <div
              className="flex items-center gap-2 px-4 py-2.5 border-b border-[#D4E8DC]"
              style={{ background: '#EEF8F2' }}
            >
              <div className="flex gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
              </div>
              <div className="flex-1 mx-6">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={current.url}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                    className="bg-white rounded-md px-3 py-1 text-[11px] text-[#4A6456] font-mono text-center border border-[#CCE9DA]"
                  >
                    {current.url}
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>

            {/* Área da screenshot */}
            <div className="relative overflow-hidden" style={{ background: '#f0f4f1', minHeight: '320px' }}>
              <AnimatePresence mode="wait">
                <motion.div
                  key={current.file}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                >
                  <img
                    src={`/screenshots/${current.file}`}
                    alt={current.label}
                    className="w-full block"
                  />
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </ScrollReveal>

        {/* Descrição */}
        <div className="mt-6 flex justify-center">
          <AnimatePresence mode="wait">
            <motion.p
              key={current.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="text-sm text-[#4A6456] text-center max-w-lg leading-relaxed"
            >
              {current.description}
            </motion.p>
          </AnimatePresence>
        </div>
      </div>
    </section>
  )
}
