import { Monitor, HardDrives, Brain, Cloud } from '@phosphor-icons/react'
import ScrollReveal from '../components/ScrollReveal'
import type { Icon } from '@phosphor-icons/react'

interface Stack {
  icon: Icon
  title: string
  accentColor: string
  techs: string[]
}

const stacks: Stack[] = [
  {
    icon: Monitor,
    title: 'Frontend',
    accentColor: '#00703C',
    techs: ['React 18', 'Vite', 'Tailwind CSS v4', 'Zustand', 'TanStack Query', 'Phosphor Icons'],
  },
  {
    icon: HardDrives,
    title: 'Backend',
    accentColor: '#116DFF',
    techs: ['FastAPI', 'SQLAlchemy 2.0', 'aiosqlite', 'Pydantic', 'JWT / bcrypt', 'slowapi'],
  },
  {
    icon: Brain,
    title: 'Inteligência Artificial',
    accentColor: '#F59E0B',
    techs: ['OpenAI Responses API', 'Structured Outputs', 'RAG file_search', 'pdfplumber'],
  },
  {
    icon: Cloud,
    title: 'Infraestrutura',
    accentColor: '#10B981',
    techs: ['Oracle Cloud', 'Ubuntu 24.04', 'Nginx', 'systemd', "Let's Encrypt", 'fail2ban'],
  },
]

export default function TechStack() {
  return (
    <section id="tech-stack" className="py-24 lg:py-32" style={{ background: '#ffffff' }}>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <div className="flex flex-col items-center text-center gap-4 mb-16">
            <span className="section-badge">Tecnologias</span>
            <h2
              className="font-display font-bold text-[#0f1a12] leading-tight"
              style={{ fontSize: 'clamp(1.75rem, 4vw, 2.5rem)', letterSpacing: '-0.025em' }}
            >
              Stack moderna para compliance robusto.
            </h2>
            <p className="text-lg text-[#4A6456] leading-relaxed max-w-2xl">
              Cada tecnologia escolhida com propósito — da IA generativa à infraestrutura
              confiável na nuvem.
            </p>
          </div>
        </ScrollReveal>

        {/* Grade editorial com dividers */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 sm:divide-x sm:divide-[#E2EFE8]">
          {stacks.map((stack, i) => (
            <ScrollReveal key={stack.title} delay={i * 0.1}>
              <div className="px-0 sm:px-8 py-8 sm:py-0 first:pl-0 last:pr-0 flex flex-col gap-5 border-b sm:border-b-0 border-[#E2EFE8] last:border-b-0">
                {/* Barra de cor */}
                <div
                  className="w-8 h-[3px] rounded-full"
                  style={{ backgroundColor: stack.accentColor }}
                />

                {/* Ícone + título */}
                <div className="flex items-center gap-2.5">
                  <stack.icon size={17} weight="duotone" style={{ color: stack.accentColor }} />
                  <h3
                    className="font-display font-semibold text-[#0f1a12] text-sm"
                    style={{ letterSpacing: '-0.01em' }}
                  >
                    {stack.title}
                  </h3>
                </div>

                {/* Lista de tecnologias */}
                <ul className="flex flex-col gap-2">
                  {stack.techs.map(tech => (
                    <li key={tech} className="flex items-center gap-2.5">
                      <span
                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: stack.accentColor, opacity: 0.5 }}
                      />
                      <span className="font-mono text-[12px] text-[#4A6456] leading-none">
                        {tech}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  )
}
