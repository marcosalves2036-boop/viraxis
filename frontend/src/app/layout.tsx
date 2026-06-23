import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'VIRAXIS — Conteúdo Viral Autônomo',
  description: 'Plataforma de geração autônoma de conteúdo viral',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  )
}
