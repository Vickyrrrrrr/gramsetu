'use client'

import Link from 'next/link'

export function Nav({ links }: { links: { href: string; label: string }[] }) {
  return (
    <nav
      className="fixed top-0 inset-x-0 z-50 flex items-center justify-between px-6 h-16"
      style={{
        background: 'rgba(245,245,245,0.88)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--hairline)',
      }}
    >
      <Link href="/" className="text-xl font-light tracking-[-0.02em]" style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}>
        GramSetu
      </Link>
      <div className="flex items-center gap-6 text-nav-link" style={{ color: 'var(--body)' }}>
        {links.map((l) => (
          <a
            key={l.href}
            href={l.href}
            className="transition-colors duration-150 hover:text-ink"
          >
            {l.label}
          </a>
        ))}
        <Link
          href="/app"
          className="btn-primary"
        >
          Try it &rarr;
        </Link>
      </div>
    </nav>
  )
}

export function Footer() {
  return (
    <footer style={{ borderTop: '1px solid var(--hairline)', background: 'var(--canvas)' }}>
      <div className="max-w-[1200px] mx-auto px-6 py-12 flex items-center justify-between text-body-sm" style={{ color: 'var(--body)' }}>
        <span className="text-base" style={{ fontFamily: "'Instrument Serif', Georgia, serif", color: 'var(--ink)' }}>
          GramSetu
        </span>
        <span>Built for Bharat</span>
        <div className="flex gap-4">
          <a
            href="https://github.com/Vickyrrrrrr/gramsetu"
            target="_blank"
            rel="noopener noreferrer"
            className="transition-colors duration-150 hover:text-ink"
          >
            GitHub
          </a>
          <Link href="/terms" className="transition-colors duration-150 hover:text-ink">
            Terms
          </Link>
          <Link href="/admin" className="transition-colors duration-150 hover:text-ink">
            Admin
          </Link>
        </div>
      </div>
    </footer>
  )
}
