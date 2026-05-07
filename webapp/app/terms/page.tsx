'use client'

import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import { Nav, Footer } from '@/components/nav-footer'

const NAV_LINKS = [
  { href: '#how', label: 'How it works' },
  { href: '#forms', label: 'Services' },
]

const SECTIONS = [
  {
    title: '1. Acceptance of Terms',
    body: 'By accessing or using GramSetu ("the Service"), you agree to be bound by these Terms of Service. If you do not agree, please do not use the Service. GramSetu is an AI-powered assistant that helps users fill government forms and access scheme information.',
  },
  {
    title: '2. Service Description',
    body: (
      <>
        <p className="mb-2">GramSetu provides an AI conversational interface that assists users in:</p>
        <ul className="list-disc pl-5 space-y-1 mb-2">
          <li>Understanding eligibility for Indian government schemes and services</li>
          <li>Collecting and organizing information needed for government form submissions</li>
          <li>Filling government portal forms using automated browser technology</li>
          <li>Providing information about government processes and requirements</li>
        </ul>
        <p>
          GramSetu <strong>does not</strong> guarantee form approval, scheme eligibility, or benefit disbursement.
          Final decisions rest solely with the respective government authorities.
        </p>
      </>
    ),
  },
  {
    title: '3. User Responsibilities',
    body: (
      <>
        <p className="mb-2">By using GramSetu, you agree that:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>All information you provide is true, accurate, and belongs to you or a person you are legally authorized to represent</li>
          <li>You will not submit false, forged, or fraudulent documents or information</li>
          <li>You are responsible for verifying the accuracy of information before submission</li>
          <li>You will not use the Service for any illegal or unauthorized purpose</li>
          <li>You understand that impersonating another person or submitting false information may constitute a criminal offense under Indian law</li>
        </ul>
      </>
    ),
  },
  {
    title: '4. Privacy & Data Protection',
    body: (
      <>
        <p className="mb-2">GramSetu handles your data in compliance with the Digital Personal Data Protection Act, 2023 (DPDP Act):</p>
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>Local encryption:</strong> User-provided identity data (Aadhaar, PAN, bank details, address) is encrypted using AES-256-GCM before storage. Encryption keys are derived from your personal password and never leave your device.</li>
          <li><strong>Zero-knowledge architecture:</strong> GramSetu cannot access your decrypted vault data. If you lose your vault password, your encrypted data cannot be recovered.</li>
          <li><strong>Session-only PII:</strong> Identity data used during a form-filling session is encrypted in transit (HTTPS) and never written to server logs in plaintext.</li>
          <li><strong>Data minimization:</strong> We collect only the information necessary to complete your requested form. No data is sold, shared with third parties, or used for advertising.</li>
          <li><strong>Right to erasure:</strong> You may delete your data at any time by clearing your browser&rsquo;s local storage or using the &ldquo;New Conversation&rdquo; button.</li>
        </ul>
      </>
    ),
  },
  {
    title: '5. Identity Verification',
    body: 'GramSetu performs mathematical validation on Aadhaar numbers (Verhoeff checksum) and detects obviously fraudulent patterns (all-identical digits, sequential numbers). This verification is a mathematical integrity check only — it does not constitute authentication by UIDAI. A valid checksum does not guarantee that the Aadhaar belongs to you. We strongly recommend that service providers perform independent identity verification before processing applications.',
  },
  {
    title: '6. Limitation of Liability',
    body: (
      <>
        <p className="mb-2">GramSetu is provided &ldquo;as is&rdquo; without warranty of any kind. We do not warrant that:</p>
        <ul className="list-disc pl-5 space-y-1 mb-2">
          <li>The Service will be uninterrupted or error-free</li>
          <li>Government portals will accept automated form submissions</li>
          <li>AI-generated responses will always be accurate or complete</li>
          <li>Scheme eligibility determinations are definitive</li>
        </ul>
        <p>
          To the fullest extent permitted by law, GramSetu and its creators shall not be liable for any direct,
          indirect, incidental, or consequential damages arising from use of the Service, including but not limited
          to: missed benefits, rejected applications, or inaccurate information submitted through the Service.
        </p>
      </>
    ),
  },
  {
    title: '7. Third-Party Services',
    body: 'GramSetu integrates with third-party AI providers (Sarvam AI, Groq, NVIDIA) for natural language processing, speech recognition, and text-to-speech. Data sent to these providers is governed by their respective privacy policies. GramSetu also automates government portals using browser technology — interactions with these portals are governed by the respective government\'s terms of service.',
  },
  {
    title: '8. Prohibited Uses',
    body: (
      <>
        <p className="mb-2">You may not use GramSetu to:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>Submit applications on behalf of another person without their explicit consent</li>
          <li>Automate mass form submissions or engage in any activity that overloads government servers</li>
          <li>Collect or harvest personal data of other users</li>
          <li>Use the Service for any fraudulent, deceptive, or unlawful purpose</li>
          <li>Reverse engineer, decompile, or attempt to extract the source code of the Service</li>
        </ul>
      </>
    ),
  },
  {
    title: '9. Intellectual Property',
    body: 'GramSetu is open-source software released under the MIT License. The GramSetu name, logo, and branding are the property of the GramSetu project. Government form content, scheme information, and portal designs are the property of their respective government owners.',
  },
  {
    title: '10. Modifications to Terms',
    body: 'We reserve the right to update these Terms at any time. Material changes will be communicated through the Service. Continued use of GramSetu after changes constitutes acceptance of the updated Terms.',
  },
  {
    title: '11. Governing Law',
    body: 'These Terms shall be governed by and construed in accordance with the laws of India. Any disputes arising from these Terms shall be subject to the exclusive jurisdiction of courts in New Delhi, India.',
  },
  {
    title: '12. Contact',
    body: (
      <>
        For questions about these Terms, privacy concerns, or to report misuse, please open an issue on our{' '}
        <a
          href="https://github.com/Vickyrrrrrr/gramsetu"
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
          style={{ color: 'var(--ink)' }}
        >
          GitHub repository
        </a>{' '}
        or contact the project maintainer.
      </>
    ),
  },
]

export default function TermsPage() {
  return (
    <div style={{ background: 'var(--canvas)' }}>
      <Nav links={NAV_LINKS} />

      <section style={{ paddingTop: 128, paddingBottom: 96 }}>
        <div className="max-w-3xl mx-auto px-6" style={{ color: 'var(--ink)' }}>
          <p className="mb-4 tracking-[0.96px] uppercase font-semibold" style={{ fontSize: 12, color: 'var(--muted)' }}>
            Legal
          </p>
          <h1
            className="mb-2"
            style={{
              fontFamily: "'Instrument Serif', Georgia, serif",
              fontWeight: 300,
              fontSize: 'clamp(2rem, 5vw, 48px)',
              lineHeight: 1.08,
              letterSpacing: '-0.96px',
            }}
          >
            Terms of Service
          </h1>
          <p style={{ fontSize: 15, color: 'var(--muted)' }}>
            Last updated: May 2026
          </p>

          <div className="mt-16 space-y-12" style={{ fontSize: 15, lineHeight: 1.7, letterSpacing: '0.15px', color: 'var(--body)' }}>
            {SECTIONS.map((s) => (
              <section key={s.title}>
                <h2
                  className="mb-3"
                  style={{
                    fontFamily: "'Instrument Serif', Georgia, serif",
                    fontWeight: 300,
                    fontSize: 24,
                    lineHeight: 1.2,
                    color: 'var(--ink)',
                  }}
                >
                  {s.title}
                </h2>
                {typeof s.body === 'string' ? <p>{s.body}</p> : s.body}
              </section>
            ))}
          </div>

          <div className="mt-16 pt-12" style={{ borderTop: '1px solid var(--hairline)' }}>
            <p style={{ fontSize: 15, color: 'var(--body)', marginBottom: 16 }}>
              Ready to use GramSetu?
            </p>
            <Link href="/app" className="btn-primary">
              Open GramSetu <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  )
}
