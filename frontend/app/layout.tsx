import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { AppProviders } from '@/components/AppProviders'
import './globals.css'

export const metadata: Metadata = {
  title: 'CampusPilot',
  description: 'Campus AI assistant for UMD students',
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