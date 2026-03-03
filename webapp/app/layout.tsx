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
        {/* Geist font via Vercel CDN */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap"
        />
        <style>{`
          @import url('https://fonts.cdnfonts.com/css/geist');
        `}</style>
      </head>
      <body className="bg-cream text-ink antialiased">{children}</body>
    </html>
  )
}
