'use client'

import Link from 'next/link'
import { ArrowRight, Mic, FileText, CheckCircle, Globe, MessageSquare, Zap } from 'lucide-react'

/* ── tiny components ─────────────────────────────────────────── */

function Nav() {
  return (
    <nav className="fixed top-0 inset-x-0 z-50 flex items-center justify-between px-6 py-4"
         style={{ background: 'rgba(247,246,243,0.88)', backdropFilter: 'blur(10px)',
                  borderBottom: '1px solid #E5E5E0' }}>
      <span className="serif text-xl font-normal tracking-tight">GramSetu</span>
      <div className="flex items-center gap-6 text-sm" style={{ color: '#6B6B6B' }}>
        <a href="#how" className="hover:text-[#0C0C0C] transition-colors">How it works</a>
        <a href="#forms" className="hover:text-[#0C0C0C] transition-colors">Services</a>
        <a href="#languages" className="hover:text-[#0C0C0C] transition-colors">Languages</a>
        <Link href="/app"
          className="rounded-full px-4 py-1.5 text-sm font-medium transition-opacity hover:opacity-80"
          style={{ background: '#0C0C0C', color: '#F7F6F3' }}>
          Try it →
        </Link>
      </div>
    </nav>
  )
}

function Divider() {
  return <div style={{ borderTop: '1px solid #E5E5E0' }} />
}

/* ── landing page ────────────────────────────────────────────── */

export default function LandingPage() {
  return (
    <div className="min-h-screen" style={{ background: '#F7F6F3' }}>
      <Nav />

      {/* ── Hero ── */}
      <section className="pt-40 pb-28 px-6 max-w-5xl mx-auto">
        <p className="text-sm font-medium mb-6 tracking-widest uppercase"
           style={{ color: '#6B6B6B' }}>
          For 1.4 billion Indians
        </p>
        <h1 className="serif font-normal leading-none tracking-tight mb-8"
            style={{ fontSize: 'clamp(3rem, 7vw, 5.5rem)', maxWidth: 840 }}>
          Government forms,
          <br />
          <em>filled automatically.</em>
        </h1>
        <p className="text-xl leading-relaxed mb-10 max-w-xl" style={{ color: '#6B6B6B' }}>
          Speak in Hindi, Tamil, Bengali — or any of India's 22 languages.
          GramSetu understands you and fills the form on your behalf.
        </p>
        <div className="flex items-center gap-4 flex-wrap">
          <Link href="/app"
            className="inline-flex items-center gap-2 rounded-full px-6 py-3 text-base font-medium transition-opacity hover:opacity-80"
            style={{ background: '#0C0C0C', color: '#F7F6F3' }}>
            Try for free <ArrowRight size={16} />
          </Link>
          <a href="#how"
            className="text-base font-medium transition-colors hover:opacity-60 flex items-center gap-1"
            style={{ color: '#0C0C0C' }}>
            See how it works ↓
          </a>
        </div>

        {/* Stats row */}
        <div className="mt-20 grid grid-cols-3 gap-px"
             style={{ borderTop: '1px solid #E5E5E0', borderBottom: '1px solid #E5E5E0', maxWidth: 480 }}>
          {[
            { n: '12', label: 'Government schemes' },
            { n: '10+', label: 'Indian languages' },
            { n: '< 60s', label: 'To submit a form' },
          ].map(({ n, label }) => (
            <div key={label} className="py-5 pr-6">
              <p className="serif text-3xl">{n}</p>
              <p className="text-sm mt-1" style={{ color: '#6B6B6B' }}>{label}</p>
            </div>
          ))}
        </div>
      </section>

      <Divider />

      {/* ── Problem ── */}
      <section className="py-28 px-6 max-w-5xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-16 items-start">
          <div>
            <p className="text-xs tracking-widest uppercase mb-4" style={{ color: '#6B6B6B' }}>The problem</p>
            <h2 className="serif font-normal leading-tight mb-6"
                style={{ fontSize: 'clamp(2rem, 4vw, 3rem)' }}>
              One crore people miss out on benefits they're entitled to.
              <em> Every year.</em>
            </h2>
          </div>
          <div className="space-y-6 pt-2" style={{ color: '#6B6B6B', lineHeight: '1.7' }}>
            <p>
              Ration cards, pension, PM-KISAN, Ayushman Bharat — the schemes exist.
              The money is allocated. But a 70-year-old farmer in Barabanki can't fill
              a 14-page PDF in English.
            </p>
            <p>
              Middlemen charge ₹500–₹2000 to do what the government offers for free.
              GramSetu ends that.
            </p>
            <p>
              You speak. We fill. You get what you're owed.
            </p>
          </div>
        </div>
      </section>

      <Divider />

      {/* ── How it works ── */}
      <section id="how" className="py-28 px-6 max-w-5xl mx-auto">
        <p className="text-xs tracking-widest uppercase mb-4" style={{ color: '#6B6B6B' }}>How it works</p>
        <h2 className="serif font-normal mb-16" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)' }}>
          Three steps from voice to approval.
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-px"
             style={{ border: '1px solid #E5E5E0', borderRadius: 8, overflow: 'hidden' }}>
          {[
            {
              icon: <Mic size={22} />, step: '01',
              title: 'You speak',
              body: 'Click the mic or type in any language — "मुझे राशन कार्ड चाहिए" or "I need a ration card". GramSetu detects it automatically.',
            },
            {
              icon: <FileText size={22} />, step: '02',
              title: 'We fill',
              body: 'GramSetu connects to DigiLocker, fetches your Aadhaar, opens the government portal, and fills every field. No typing.',
            },
            {
              icon: <CheckCircle size={22} />, step: '03',
              title: 'You confirm',
              body: 'Review, enter the OTP from your phone, and the form is submitted. You get a reference number by SMS.',
            },
          ].map(({ icon, step, title, body }) => (
            <div key={step} className="p-8" style={{ background: 'white' }}>
              <div className="flex items-center justify-between mb-6">
                {icon}
                <span className="text-4xl font-light serif" style={{ color: '#E5E5E0' }}>{step}</span>
              </div>
              <h3 className="text-lg font-semibold mb-3">{title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: '#6B6B6B' }}>{body}</p>
            </div>
          ))}
        </div>
      </section>

      <Divider />

      {/* ── Forms ── */}
      <section id="forms" className="py-28 px-6 max-w-5xl mx-auto">
        <p className="text-xs tracking-widest uppercase mb-4" style={{ color: '#6B6B6B' }}>Supported services</p>
        <h2 className="serif font-normal mb-16" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)' }}>
          Every scheme that matters.
        </h2>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            '🍚 Ration Card',
            '📇 PAN Card',
            '🗳️ Voter ID',
            '👴 Old Age Pension',
            '🏥 Ayushman Bharat',
            '🌾 PM-KISAN',
            '👷 MNREGA Job Card',
            '👶 Birth Certificate',
            '📜 Caste Certificate',
            '🏦 Jan Dhan Account',
            '💳 Kisan Credit Card',
            '+ more coming',
          ].map((form) => (
            <div key={form}
                 className="px-4 py-3 text-sm rounded-lg transition-colors cursor-default"
                 style={{ border: '1px solid #E5E5E0', background: 'white', color: '#0C0C0C' }}>
              {form}
            </div>
          ))}
        </div>
      </section>

      <Divider />

      {/* ── Languages ── */}
      <section id="languages" className="py-28 px-6 max-w-5xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-16 items-center">
          <div>
            <p className="text-xs tracking-widest uppercase mb-4" style={{ color: '#6B6B6B' }}>Languages</p>
            <h2 className="serif font-normal mb-6" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)' }}>
              India's languages are our interface.
            </h2>
            <p className="leading-relaxed" style={{ color: '#6B6B6B' }}>
              Not English. Not Hindi only. GramSetu detects and responds in the language
              you use — automatically.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            {[
              { code: 'HI', name: 'हिंदी' },
              { code: 'TA', name: 'தமிழ்' },
              { code: 'TE', name: 'తెలుగు' },
              { code: 'BN', name: 'বাংলা' },
              { code: 'GU', name: 'ગુજરાતી' },
              { code: 'KN', name: 'ಕನ್ನಡ' },
              { code: 'ML', name: 'മലയാളം' },
              { code: 'PA', name: 'ਪੰਜਾਬੀ' },
              { code: 'UR', name: 'اردو' },
              { code: 'MR', name: 'मराठी' },
              { code: 'EN', name: 'English' },
            ].map(({ code, name }) => (
              <div key={code}
                   className="px-4 py-2 rounded-full text-sm font-medium"
                   style={{ border: '1px solid #E5E5E0', background: 'white' }}>
                {name}
              </div>
            ))}
          </div>
        </div>
      </section>

      <Divider />

      {/* ── CTA ── */}
      <section className="py-28 px-6 max-w-5xl mx-auto text-center">
        <h2 className="serif font-normal mb-6"
            style={{ fontSize: 'clamp(2.5rem, 5vw, 4rem)' }}>
          Try it now.
          <br />
          <em>It takes 60 seconds.</em>
        </h2>
        <p className="mb-8 text-lg" style={{ color: '#6B6B6B' }}>
          No signup. No credit card. Just speak.
        </p>
        <Link href="/app"
          className="inline-flex items-center gap-2 rounded-full px-8 py-4 text-base font-medium transition-opacity hover:opacity-80"
          style={{ background: '#0C0C0C', color: '#F7F6F3' }}>
          Open GramSetu <ArrowRight size={16} />
        </Link>
      </section>

      {/* ── Footer ── */}
      <footer style={{ borderTop: '1px solid #E5E5E0' }}>
        <div className="max-w-5xl mx-auto px-6 py-8 flex items-center justify-between text-sm"
             style={{ color: '#6B6B6B' }}>
          <span className="serif text-base" style={{ color: '#0C0C0C' }}>GramSetu</span>
          <span>Built for Bharat. Built with ❤️</span>
          <div className="flex gap-4">
            <a href="https://github.com/Vickyrrrrrr/gramsetu" target="_blank" rel="noopener noreferrer" className="hover:text-[#0C0C0C] transition-colors">GitHub</a>
            <a href="#" className="hover:text-[#0C0C0C] transition-colors">Docs</a>
            <Link href="/admin" className="hover:text-[#0C0C0C] transition-colors">Admin</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
