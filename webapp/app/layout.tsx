import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'GramSetu — Government Forms, Simplified',
  description:
    'AI-powered form filling for every Indian. Speak in your language, we fill the form.',
  openGraph: {
    title: 'GramSetu',
    description: 'Government forms, simplified. Speak in your language.',
    siteName: 'GramSetu',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300;400;500;600&display=swap"
        />
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏛️</text></svg>" />
      </head>
      <body className="bg-canvas text-ink antialiased">{children}</body>
    </html>
  )
}
