'use client'

import Link from 'next/link'
import { ArrowRight } from 'lucide-react'

function Nav() {
  return (
    <nav className="fixed top-0 inset-x-0 z-50 flex items-center justify-between px-6 py-4"
         style={{ background: 'rgba(247,246,243,0.88)', backdropFilter: 'blur(10px)',
                  borderBottom: '1px solid #E5E5E0' }}>
      <Link href="/" className="serif text-xl font-normal tracking-tight" style={{ color: '#0C0C0C' }}>GramSetu</Link>
      <div className="flex items-center gap-6 text-sm" style={{ color: '#6B6B6B' }}>
        <Link href="/app"
          className="rounded-full px-4 py-1.5 text-sm font-medium transition-opacity hover:opacity-80"
          style={{ background: '#0C0C0C', color: '#F7F6F3' }}>
          Try it →
        </Link>
      </div>
    </nav>
  )
}

export default function TermsPage() {
  return (
    <div className="min-h-screen" style={{ background: '#F7F6F3', fontFamily: 'system-ui, sans-serif' }}>
      <Nav />

      <section className="pt-32 pb-16 px-6 max-w-3xl mx-auto" style={{ color: '#0C0C0C' }}>
        <p className="text-sm font-medium mb-4 tracking-widest uppercase" style={{ color: '#6B6B6B' }}>
          Legal
        </p>
        <h1 className="serif font-normal leading-tight mb-2"
            style={{ fontSize: 'clamp(2rem, 5vw, 3.5rem)' }}>
          Terms of Service
        </h1>
        <p className="text-sm mb-12" style={{ color: '#6B6B6B' }}>
          Last updated: May 2026
        </p>

        <div className="space-y-12 text-sm leading-relaxed" style={{ color: '#444' }}>

          {/* 1 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>1. Acceptance of Terms</h2>
            <p>
              By accessing or using GramSetu (&ldquo;the Service&rdquo;), you agree to be bound by these Terms of Service.
              If you do not agree, please do not use the Service. GramSetu is an AI-powered assistant that helps users
              fill government forms and access scheme information.
            </p>
          </section>

          {/* 2 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>2. Service Description</h2>
            <p className="mb-2">
              GramSetu provides an AI conversational interface that assists users in:
            </p>
            <ul className="list-disc pl-5 space-y-1">
              <li>Understanding eligibility for Indian government schemes and services</li>
              <li>Collecting and organizing information needed for government form submissions</li>
              <li>Filling government portal forms using automated browser technology</li>
              <li>Providing information about government processes and requirements</li>
            </ul>
            <p className="mt-2">
              GramSetu <strong>does not</strong> guarantee form approval, scheme eligibility, or benefit disbursement.
              Final decisions rest solely with the respective government authorities.
            </p>
          </section>

          {/* 3 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>3. User Responsibilities</h2>
            <p className="mb-2">By using GramSetu, you agree that:</p>
            <ul className="list-disc pl-5 space-y-1">
              <li>All information you provide is true, accurate, and belongs to you or a person you are legally authorized to represent</li>
              <li>You will not submit false, forged, or fraudulent documents or information</li>
              <li>You are responsible for verifying the accuracy of information before submission</li>
              <li>You will not use the Service for any illegal or unauthorized purpose</li>
              <li>You understand that impersonating another person or submitting false information may constitute a criminal offense under Indian law</li>
            </ul>
          </section>

          {/* 4 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>4. Privacy &amp; Data Protection</h2>
            <p className="mb-2">
              GramSetu handles your data in compliance with the Digital Personal Data Protection Act, 2023 (DPDP Act):
            </p>
            <ul className="list-disc pl-5 space-y-1">
              <li><strong>Local encryption:</strong> User-provided identity data (Aadhaar, PAN, bank details, address) is encrypted using AES-256-GCM before storage. Encryption keys are derived from your personal password and never leave your device.</li>
              <li><strong>Zero-knowledge architecture:</strong> GramSetu cannot access your decrypted vault data. If you lose your vault password, your encrypted data cannot be recovered.</li>
              <li><strong>Session-only PII:</strong> Identity data used during a form-filling session is encrypted in transit (HTTPS) and never written to server logs in plaintext.</li>
              <li><strong>Data minimization:</strong> We collect only the information necessary to complete your requested form. No data is sold, shared with third parties, or used for advertising.</li>
              <li><strong>Right to erasure:</strong> You may delete your data at any time by clearing your browser&rsquo;s local storage or using the &ldquo;New Conversation&rdquo; button.</li>
            </ul>
          </section>

          {/* 5 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>5. Identity Verification</h2>
            <p>
              GramSetu performs mathematical validation on Aadhaar numbers (Verhoeff checksum) and detects obviously
              fraudulent patterns (all-identical digits, sequential numbers). This verification is a mathematical integrity
              check only — it does not constitute authentication by UIDAI. A valid checksum does not guarantee that the
              Aadhaar belongs to you. We strongly recommend that service providers perform independent identity verification
              before processing applications.
            </p>
          </section>

          {/* 6 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>6. Limitation of Liability</h2>
            <p>
              GramSetu is provided &ldquo;as is&rdquo; without warranty of any kind. We do not warrant that:
            </p>
            <ul className="list-disc pl-5 space-y-1 mt-2">
              <li>The Service will be uninterrupted or error-free</li>
              <li>Government portals will accept automated form submissions</li>
              <li>AI-generated responses will always be accurate or complete</li>
              <li>Scheme eligibility determinations are definitive</li>
            </ul>
            <p className="mt-2">
              To the fullest extent permitted by law, GramSetu and its creators shall not be liable for any direct,
              indirect, incidental, or consequential damages arising from use of the Service, including but not limited
              to: missed benefits, rejected applications, or inaccurate information submitted through the Service.
            </p>
          </section>

          {/* 7 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>7. Third-Party Services</h2>
            <p>
              GramSetu integrates with third-party AI providers (Sarvam AI, Groq, NVIDIA) for natural language
              processing, speech recognition, and text-to-speech. Data sent to these providers is governed by their
              respective privacy policies. GramSetu also automates government portals using browser technology —
              interactions with these portals are governed by the respective government&rsquo;s terms of service.
            </p>
          </section>

          {/* 8 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>8. Prohibited Uses</h2>
            <p className="mb-2">You may not use GramSetu to:</p>
            <ul className="list-disc pl-5 space-y-1">
              <li>Submit applications on behalf of another person without their explicit consent</li>
              <li>Automate mass form submissions or engage in any activity that overloads government servers</li>
              <li>Collect or harvest personal data of other users</li>
              <li>Use the Service for any fraudulent, deceptive, or unlawful purpose</li>
              <li>Reverse engineer, decompile, or attempt to extract the source code of the Service</li>
            </ul>
          </section>

          {/* 9 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>9. Intellectual Property</h2>
            <p>
              GramSetu is open-source software released under the MIT License. The GramSetu name, logo, and branding
              are the property of the GramSetu project. Government form content, scheme information, and portal designs
              are the property of their respective government owners.
            </p>
          </section>

          {/* 10 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>10. Modifications to Terms</h2>
            <p>
              We reserve the right to update these Terms at any time. Material changes will be communicated through
              the Service. Continued use of GramSetu after changes constitutes acceptance of the updated Terms.
            </p>
          </section>

          {/* 11 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>11. Governing Law</h2>
            <p>
              These Terms shall be governed by and construed in accordance with the laws of India. Any disputes
              arising from these Terms shall be subject to the exclusive jurisdiction of courts in New Delhi, India.
            </p>
          </section>

          {/* 12 */}
          <section>
            <h2 className="serif text-lg font-normal mb-3" style={{ color: '#0C0C0C' }}>12. Contact</h2>
            <p>
              For questions about these Terms, privacy concerns, or to report misuse, please open an issue on our{' '}
              <a href="https://github.com/Vickyrrrrrr/gramsetu" target="_blank" rel="noopener noreferrer"
                 className="underline" style={{ color: '#0C0C0C' }}>
                GitHub repository
              </a>{' '}or contact the project maintainer.
            </p>
          </section>

        </div>

        {/* CTA */}
        <div className="mt-16 pt-12" style={{ borderTop: '1px solid #E5E5E0' }}>
          <p className="text-sm mb-4" style={{ color: '#6B6B6B' }}>
            Ready to use GramSetu?
          </p>
          <Link href="/app"
            className="inline-flex items-center gap-2 rounded-full px-8 py-4 text-base font-medium transition-opacity hover:opacity-80"
            style={{ background: '#0C0C0C', color: '#F7F6F3' }}>
            Open GramSetu <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ borderTop: '1px solid #E5E5E0' }}>
        <div className="max-w-5xl mx-auto px-6 py-8 flex items-center justify-between text-sm"
             style={{ color: '#6B6B6B' }}>
          <Link href="/" className="serif text-base" style={{ color: '#0C0C0C' }}>GramSetu</Link>
          <span>Built for Bharat. Built with ❤️</span>
          <div className="flex gap-4">
            <a href="https://github.com/Vickyrrrrrr/gramsetu" target="_blank" rel="noopener noreferrer"
               className="hover:text-[#0C0C0C] transition-colors">GitHub</a>
            <Link href="/terms" className="hover:text-[#0C0C0C] transition-colors" style={{ color: '#0C0C0C', fontWeight: 500 }}>Terms</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
