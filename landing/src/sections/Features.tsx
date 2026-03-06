import { FileText, GitDiff, ChatCircleDots, FolderOpen, FilePdf, ShieldCheck } from '@phosphor-icons/react'
import ScrollReveal from '../components/ScrollReveal'
import BentoFeatureCard from '../components/BentoFeatureCard'
import type { Icon } from '@phosphor-icons/react'

interface FeatureItem {
  icon: Icon
  title: string
  description: string
  accentColor: string
  gridClass: string
}

const features: FeatureItem[] = [
  {
    icon: FileText,
    title: 'Avaliação de Documentos',
    description:
      'Analise FRE, DFP, FCA ou IPE automaticamente contra 156 itens do Anexo C da CVM Resolução 80. Upload local ou seleção de documento baixado.',
    accentColor: '#00703C',
    gridClass: 'lg:col-span-2',
  },
  {
    icon: GitDiff,
    title: 'Comparação (Diff)',
    description:
      'Comparação semântica entre versões de qualquer documento CVM com análise de impacto gerada por IA.',
    accentColor: '#116DFF',
    gridClass: '',
  },
  {
    icon: ChatCircleDots,
    title: 'RAG Multi-agêntico',
    description:
      'Chat fundamentado em todos os documentos da empresa (FRE, DFP, FCA, IPE) via Vector Store OpenAI por empresa.',
    accentColor: '#F59E0B',
    gridClass: '',
  },
  {
    icon: FolderOpen,
    title: 'Arquivo Local',
    description:
      'Baixe e gerencie FRE, DFP, FCA e IPE de qualquer companhia aberta diretamente dos dados CVM. Histórico completo para consulta.',
    accentColor: '#8B5CF6',
    gridClass: '',
  },
  {
    icon: FilePdf,
    title: 'Exportação',
    description:
      'Relatórios em PDF e Excel com scores detalhados e recomendações de melhoria.',
    accentColor: '#EF4444',
    gridClass: '',
  },
  {
    icon: ShieldCheck,
    title: 'Segurança Corporativa',
    description:
      'Zero autenticação — uso local. Rate limiting, criptografia bcrypt, sem dados em nuvem.',
    accentColor: '#10B981',
    gridClass: 'lg:col-span-3',
  },
]

export default function Features() {
  return (
    <section id="features" className="py-24 lg:py-32" style={{ background: '#ffffff' }}>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <div className="flex flex-col items-center text-center gap-4 mb-14">
            <span className="section-badge">Funcionalidades</span>
            <h2
              className="font-display font-bold text-[#0f1a12] leading-tight"
              style={{ fontSize: 'clamp(1.75rem, 4vw, 2.5rem)', letterSpacing: '-0.025em' }}
            >
              FRE, DFP, FCA e IPE em um só lugar.
            </h2>
            <p className="text-lg text-[#4A6456] leading-relaxed max-w-2xl">
              Da avaliação normativa ao RAG multi-agêntico — cobertura completa para análise de
              documentos CVM de companhias abertas.
            </p>
          </div>
        </ScrollReveal>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-5">
          {features.map((feat, i) => (
            <ScrollReveal
              key={feat.title}
              delay={i * 0.07}
              className={feat.gridClass}
            >
              <BentoFeatureCard
                icon={feat.icon}
                title={feat.title}
                description={feat.description}
                accentColor={feat.accentColor}
              />
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  )
}
