import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { AppProviders } from '@/components/AppProviders'
import './globals.css'

export const metadata: Metadata = {
  title: 'TerpAI',
  description: 'AI Assistant for UMD Students',
}

export default function RootLayout({
  children,
}: {
  children: ReactNode
}) {
  return (
    <html lang="en">
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  )
}