'use client'

import Link from 'next/link'
import { ArrowRight, Mic, FileText, CheckCircle } from 'lucide-react'
import { Nav, Footer } from '@/components/nav-footer'

function GradientOrb({
  color,
  size,
  className,
}: {
  color: 'mint' | 'peach' | 'lavender' | 'sky' | 'rose'
  size: number
  className?: string
}) {
  return (
    <div
      className={`gradient-orb gradient-orb-${color} ${className || ''}`}
      style={{ width: size, height: size }}
    />
  )
}

function Divider() {
  return <div style={{ borderTop: '1px solid var(--hairline)' }} />
}

const NAV_LINKS = [
  { href: '#how', label: 'How it works' },
  { href: '#forms', label: 'Services' },
  { href: '#languages', label: 'Languages' },
]

const SCHEMES = [
  'Ration Card',
  'PAN Card',
  'Voter ID',
  'Old Age Pension',
  'Ayushman Bharat',
  'PM-KISAN',
  'MNREGA Job Card',
  'Birth Certificate',
  'Caste Certificate',
  'Jan Dhan Account',
  'Kisan Credit Card',
  '+ more coming',
]

const LANGUAGES = [
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
]

export default function LandingPage() {
  return (
    <div style={{ background: 'var(--canvas)' }}>
      <Nav links={NAV_LINKS} />

      {/* ═══ Hero Band ═══ */}
      <section className="relative overflow-hidden" style={{ background: 'var(--canvas)', paddingTop: 160, paddingBottom: 96 }}>
        <GradientOrb color="mint" size={680} className="absolute -top-40 -right-40" />
        <GradientOrb color="peach" size={520} className="absolute -bottom-60 -left-32" />
        <GradientOrb color="lavender" size={400} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />

        <div className="relative z-10 max-w-[1200px] mx-auto px-6">
          <p
            className="mb-6 tracking-[0.96px] uppercase font-semibold"
            style={{ fontSize: 12, color: 'var(--muted)' }}
          >
            For 1.4 billion Indians
          </p>
          <h1
            className="mb-8"
            style={{
              fontFamily: "'Instrument Serif', Georgia, serif",
              fontWeight: 300,
              fontSize: 'clamp(3rem, 7vw, 64px)',
              lineHeight: 1.05,
              letterSpacing: '-1.92px',
              maxWidth: 840,
              color: 'var(--ink)',
            }}
          >
            Government forms,
            <br />
            <em>filled automatically.</em>
          </h1>
          <p
            className="mb-10 max-w-lg"
            style={{
              fontFamily: "'Inter', system-ui, sans-serif",
              fontSize: 16,
              lineHeight: 1.5,
              letterSpacing: '0.16px',
              color: 'var(--body)',
            }}
          >
            Speak in Hindi, Tamil, Bengali — or any of India&apos;s 22 languages.
            GramSetu understands you and fills the form on your behalf.
          </p>
          <div className="flex items-center gap-4 flex-wrap">
            <Link href="/app" className="btn-primary">
              Try for free <ArrowRight size={16} />
            </Link>
            <a href="#how" className="btn-ghost text-sm">
              See how it works &darr;
            </a>
          </div>

          <div
            className="mt-24 grid grid-cols-3 gap-px max-w-[480px]"
            style={{ borderTop: '1px solid var(--hairline)', borderBottom: '1px solid var(--hairline)' }}
          >
            {[
              { n: '12', label: 'Government schemes' },
              { n: '10+', label: 'Indian languages' },
              { n: '< 60s', label: 'To submit a form' },
            ].map(({ n, label }) => (
              <div key={label} className="py-5 pr-6">
                <p
                  className="text-4xl"
                  style={{
                    fontFamily: "'Instrument Serif', Georgia, serif",
                    fontWeight: 300,
                    color: 'var(--ink)',
                  }}
                >
                  {n}
                </p>
                <p
                  className="mt-1"
                  style={{
                    fontFamily: "'Inter', system-ui, sans-serif",
                    fontSize: 14,
                    color: 'var(--muted)',
                  }}
                >
                  {label}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <Divider />

      {/* ═══ Problem ═══ */}
      <section style={{ paddingTop: 96, paddingBottom: 96, background: 'var(--canvas)' }}>
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-16 items-start">
            <div>
              <p
                className="mb-4 tracking-[0.96px] uppercase font-semibold"
                style={{ fontSize: 12, color: 'var(--muted)' }}
              >
                The problem
              </p>
              <h2
                className="mb-6"
                style={{
                  fontFamily: "'Instrument Serif', Georgia, serif",
                  fontWeight: 300,
                  fontSize: 'clamp(2rem, 4vw, 48px)',
                  lineHeight: 1.08,
                  letterSpacing: '-0.96px',
                  color: 'var(--ink)',
                }}
              >
                One crore people miss out on benefits they&apos;re entitled to.
                <em> Every year.</em>
              </h2>
            </div>
            <div
              className="space-y-6 pt-2"
              style={{
                fontFamily: "'Inter', system-ui, sans-serif",
                fontSize: 16,
                lineHeight: 1.7,
                letterSpacing: '0.16px',
                color: 'var(--body)',
              }}
            >
              <p>
                Ration cards, pension, PM-KISAN, Ayushman Bharat — the schemes exist.
                The money is allocated. But a 70-year-old farmer in Barabanki can&apos;t fill
                a 14-page PDF in English.
              </p>
              <p>
                Middlemen charge ₹500–₹2000 to do what the government offers for free.
                GramSetu ends that.
              </p>
              <p>You speak. We fill. You get what you&apos;re owed.</p>
            </div>
          </div>
        </div>
      </section>

      <Divider />

      {/* ═══ How it works ═══ */}
      <section id="how" style={{ paddingTop: 96, paddingBottom: 96, background: 'var(--canvas)' }}>
        <div className="relative max-w-[1200px] mx-auto px-6">
          <GradientOrb color="lavender" size={500} className="absolute -top-40 -right-40" />

          <div className="relative z-10">
            <p
              className="mb-4 tracking-[0.96px] uppercase font-semibold"
              style={{ fontSize: 12, color: 'var(--muted)' }}
            >
              How it works
            </p>
            <h2
              className="mb-16"
              style={{
                fontFamily: "'Instrument Serif', Georgia, serif",
                fontWeight: 300,
                fontSize: 'clamp(2rem, 4vw, 48px)',
                lineHeight: 1.08,
                letterSpacing: '-0.96px',
                color: 'var(--ink)',
              }}
            >
              Three steps from voice to approval.
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-3" style={{ border: '1px solid var(--hairline)', borderRadius: 16, overflow: 'hidden' }}>
              {[
                {
                  icon: <Mic size={22} color="var(--ink)" />,
                  step: '01',
                  title: 'You speak',
                  body: 'Click the mic or type in any language — "मुझे राशन कार्ड चाहिए" or "I need a ration card". GramSetu detects it automatically.',
                },
                {
                  icon: <FileText size={22} color="var(--ink)" />,
                  step: '02',
                  title: 'We fill',
                  body: 'GramSetu connects to DigiLocker, fetches your Aadhaar, opens the government portal, and fills every field. No typing.',
                },
                {
                  icon: <CheckCircle size={22} color="var(--ink)" />,
                  step: '03',
                  title: 'You confirm',
                  body: 'Review, enter the OTP from your phone, and the form is submitted. You get a reference number by SMS.',
                },
              ].map(({ icon, step, title, body }) => (
                <div
                  key={step}
                  className="p-8 feature-card"
                  style={{ borderRadius: 0, border: 'none', borderRight: '1px solid var(--hairline)' }}
                >
                  <div className="flex items-center justify-between mb-6">
                    <div style={{ color: 'var(--ink)' }}>{icon}</div>
                    <span
                      className="text-5xl"
                      style={{
                        fontFamily: "'Instrument Serif', Georgia, serif",
                        fontWeight: 300,
                        color: 'var(--hairline)',
                      }}
                    >
                      {step}
                    </span>
                  </div>
                  <h3
                    className="mb-3"
                    style={{
                      fontFamily: "'Inter', system-ui, sans-serif",
                      fontSize: 20,
                      fontWeight: 500,
                      lineHeight: 1.35,
                      color: 'var(--ink)',
                    }}
                  >
                    {title}
                  </h3>
                  <p
                    style={{
                      fontFamily: "'Inter', system-ui, sans-serif",
                      fontSize: 15,
                      lineHeight: 1.5,
                      letterSpacing: '0.15px',
                      color: 'var(--body)',
                    }}
                  >
                    {body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <Divider />

      {/* ═══ Schemes ═══ */}
      <section id="forms" style={{ paddingTop: 96, paddingBottom: 96, background: 'var(--canvas)' }}>
        <div className="max-w-[1200px] mx-auto px-6">
          <p
            className="mb-4 tracking-[0.96px] uppercase font-semibold"
            style={{ fontSize: 12, color: 'var(--muted)' }}
          >
            Supported services
          </p>
          <h2
            className="mb-16"
            style={{
              fontFamily: "'Instrument Serif', Georgia, serif",
              fontWeight: 300,
              fontSize: 'clamp(2rem, 4vw, 48px)',
              lineHeight: 1.08,
              letterSpacing: '-0.96px',
              color: 'var(--ink)',
            }}
          >
            Every scheme that matters.
          </h2>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {SCHEMES.map((form) => (
              <div
                key={form}
                className="px-5 py-4 rounded-xl transition-shadow cursor-default feature-card"
                style={{ fontSize: 15, letterSpacing: '0.15px' }}
              >
                {form}
              </div>
            ))}
          </div>
        </div>
      </section>

      <Divider />

      {/* ═══ Languages ═══ */}
      <section id="languages" style={{ paddingTop: 96, paddingBottom: 96, background: 'var(--canvas)' }}>
        <div className="relative max-w-[1200px] mx-auto px-6">
          <GradientOrb color="sky" size={420} className="absolute -top-20 -left-32" />
          <GradientOrb color="rose" size={360} className="absolute -bottom-20 -right-24" />

          <div className="relative z-10 grid grid-cols-1 md:grid-cols-2 gap-16 items-center">
            <div>
              <p
                className="mb-4 tracking-[0.96px] uppercase font-semibold"
                style={{ fontSize: 12, color: 'var(--muted)' }}
              >
                Languages
              </p>
              <h2
                className="mb-6"
                style={{
                  fontFamily: "'Instrument Serif', Georgia, serif",
                  fontWeight: 300,
                  fontSize: 'clamp(2rem, 4vw, 48px)',
                  lineHeight: 1.08,
                  letterSpacing: '-0.96px',
                  color: 'var(--ink)',
                }}
              >
                India&apos;s languages are our interface.
              </h2>
              <p
                style={{
                  fontFamily: "'Inter', system-ui, sans-serif",
                  fontSize: 16,
                  lineHeight: 1.5,
                  letterSpacing: '0.16px',
                  color: 'var(--body)',
                }}
              >
                Not English. Not Hindi only. GramSetu detects and responds in the language
                you use — automatically.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              {LANGUAGES.map(({ code, name }) => (
                <div
                  key={code}
                  className="px-5 py-2.5 rounded-full text-sm font-medium bg-surface-card border border-hairline"
                >
                  {name}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══ CTA Band ═══ */}
      <section className="relative overflow-hidden" style={{ paddingTop: 96, paddingBottom: 96, background: 'var(--canvas)' }}>
        <GradientOrb color="mint" size={500} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
        <GradientOrb color="peach" size={340} className="absolute top-0 right-1/4" />
        <GradientOrb color="sky" size={300} className="absolute bottom-0 left-1/4" />

        <div className="relative z-10 max-w-[1200px] mx-auto px-6 text-center">
          <h2
            className="mb-6"
            style={{
              fontFamily: "'Instrument Serif', Georgia, serif",
              fontWeight: 300,
              fontSize: 'clamp(2.5rem, 5vw, 64px)',
              lineHeight: 1.05,
              letterSpacing: '-1.92px',
              color: 'var(--ink)',
            }}
          >
            Try it now.
            <br />
            <em>It takes 60 seconds.</em>
          </h2>
          <p
            className="mb-8"
            style={{
              fontFamily: "'Inter', system-ui, sans-serif",
              fontSize: 16,
              lineHeight: 1.5,
              letterSpacing: '0.16px',
              color: 'var(--body)',
            }}
          >
            No signup. No credit card. Just speak.
          </p>
          <Link href="/app" className="btn-primary">
            Open GramSetu <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      <Footer />
    </div>
  )
}
