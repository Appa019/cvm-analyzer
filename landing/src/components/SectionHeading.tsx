interface SectionHeadingProps {
  badge: string
  title: string
  subtitle?: string
  align?: 'center' | 'left'
  dark?: boolean
}

export default function SectionHeading({ badge, title, subtitle, align = 'center', dark = false }: SectionHeadingProps) {
  const isCenter = align === 'center'

  return (
    <div className={`flex flex-col gap-4 ${isCenter ? 'items-center text-center' : 'items-start text-left'}`}>
      <span className={dark ? 'section-badge-dark' : 'section-badge'}>{badge}</span>
      <h2
        className={`font-display font-bold leading-tight ${dark ? 'text-white' : 'text-[#1A2E23]'}`}
        style={{ fontSize: 'clamp(1.75rem, 4vw, 2.5rem)' }}
      >
        {title}
      </h2>
      {subtitle && (
        <p className={`text-lg leading-relaxed ${isCenter ? 'max-w-2xl' : 'max-w-xl'} ${dark ? 'text-white/50' : 'text-[#5A6E62]'}`}>
          {subtitle}
        </p>
      )}
    </div>
  )
}
