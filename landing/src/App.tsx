import { Header } from './sections/Header'
import { Hero } from './sections/Hero'
import { HowItWorks } from './sections/HowItWorks'
import { AnnexC } from './sections/AnnexC'
import { Stack } from './sections/Stack'
import { Footer } from './sections/Footer'

export function App() {
  return (
    <>
      <Header />
      <main>
        <Hero />
        <HowItWorks />
        <AnnexC />
        <Stack />
      </main>
      <Footer />
    </>
  )
}
