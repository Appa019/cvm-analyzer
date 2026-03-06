import type { Icon } from '@phosphor-icons/react'

interface BentoFeatureCardProps {
  icon: Icon
  title: string
  description: string
  accentColor: string
}

export default function BentoFeatureCard({
  icon: IconComponent,
  title,
  description,
  accentColor,
}: BentoFeatureCardProps) {
  return (
    <div
      className="relative group bg-white rounded-2xl border border-[#E2EFE8] p-6 flex flex-col gap-4 overflow-hidden cursor-default transition-all duration-300 hover:shadow-[0_8px_32px_rgba(0,112,60,0.14)] hover:-translate-y-0.5 hover:border-[#C5DFD0] h-full"
      style={{
        boxShadow: '0 1px 4px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
      }}
    >
      {/* Barra de acento esquerda */}
      <div
        className="absolute left-0 top-5 bottom-5 w-[3px] rounded-r-full"
        style={{ backgroundColor: accentColor }}
      />


      <div className="pl-4 flex flex-col gap-3 relative z-10">
        {/* Ícone */}
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center transition-transform duration-300 group-hover:scale-110"
          style={{ backgroundColor: `${accentColor}14` }}
        >
          <IconComponent size={20} weight="duotone" style={{ color: accentColor }} />
        </div>

        <h3 className="font-display font-semibold text-[#0f1a12] text-base leading-snug">
          {title}
        </h3>
        <p className="text-sm text-[#4A6456] leading-relaxed">{description}</p>
      </div>
    </div>
  )
}
