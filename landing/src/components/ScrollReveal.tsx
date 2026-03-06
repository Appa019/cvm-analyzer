import { motion } from 'framer-motion'
import type { ReactNode } from 'react'

interface ScrollRevealProps {
  children: ReactNode
  delay?: number
  className?: string
}

export default function ScrollReveal({ children, delay = 0, className }: ScrollRevealProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.5, ease: 'easeOut', delay }}
      className={className}
    >
      {children}
    </motion.div>
  )
}
