'use client'

import { useState } from 'react'

export default function HomePage() {
  const [phone, setPhone] = useState('')

  const whatsappNumber = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || ''
  const whatsappLink = whatsappNumber
    ? `https://wa.me/${whatsappNumber.replace(/\+/g, '')}?text=${encodeURIComponent('नमस्ते — मुझे फ़ॉर्म भरना है')}`
    : null

  // Dynamic: user can type their own number to receive a demo
  const sendDemoLink = () => {
    if (!whatsappNumber || !phone) return
    window.open(`https://wa.me/${whatsappNumber.replace(/\+/g, '')}?text=${encodeURIComponent('नमस्ते')}`)
  }

  return (
    <main style={{ minHeight: '100vh', background: '#fafafa', fontFamily: 'system-ui' }}>
      {/* Hero */}
      <section style={{ padding: '80px 20px 40px', textAlign: 'center' }}>
        <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase', color: '#059669', marginBottom: 16 }}>
          AI × Government Services
        </div>
        <h1 style={{ fontSize: 'clamp(32px, 6vw, 56px)', fontWeight: 800, lineHeight: 1.15, margin: '0 0 16px', letterSpacing: '-0.02em' }}>
          Fill any government form<br />
          <span style={{ color: '#059669' }}>on WhatsApp.</span>
        </h1>
        <p style={{ fontSize: 18, color: '#666', maxWidth: 520, margin: '0 auto 32px', lineHeight: 1.6 }}>
          GramSetu is an AI agent that fills Ration Cards, PAN, Pensions, Ayushman Bharat, PM-KISAN
          and 30+ government forms — entirely through WhatsApp chat. No apps. No websites. Just send a message.
        </p>

        {whatsappLink ? (
          <a href={whatsappLink} target="_blank" rel="noopener noreferrer"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              background: '#25D366', color: '#fff', padding: '14px 36px',
              borderRadius: 100, textDecoration: 'none', fontWeight: 700, fontSize: 18,
              boxShadow: '0 4px 24px rgba(37,211,102,0.3)',
            }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="white"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
            Open WhatsApp
          </a>
        ) : (
          <div style={{ padding: '16px 32px', background: '#fff3cd', borderRadius: 12, display: 'inline-block' }}>
            <p style={{ color: '#856404', fontSize: 14 }}>Set NEXT_PUBLIC_WHATSAPP_NUMBER in .env to enable the WhatsApp link</p>
          </div>
        )}

        <p style={{ fontSize: 13, color: '#999', marginTop: 20 }}>
          Works on any phone with WhatsApp. No app install needed.
        </p>
      </section>

      {/* How it works */}
      <section style={{ maxWidth: 800, margin: '0 auto', padding: '40px 20px' }}>
        <h2 style={{ textAlign: 'center', fontSize: 24, fontWeight: 700, marginBottom: 40 }}>How it works</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 20 }}>
          {[
            { step: '1', title: 'Save the number', desc: 'Add GramSetu to your WhatsApp contacts — just like saving any phone number.' },
            { step: '2', title: 'Send a message', desc: 'Type "राशन कार्ड चाहिए" or send a voice note in any Indian language.' },
            { step: '3', title: 'Share details', desc: 'The AI asks for your name, Aadhaar, address — like talking to a government officer.' },
            { step: '4', title: 'Form submitted', desc: 'GramSetu fills the form on the real government portal. You get a screenshot & receipt.' },
          ].map(item => (
            <div key={item.step} style={{ background: '#fff', padding: 24, borderRadius: 12, border: '1px solid #eee' }}>
              <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#059669', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 700, marginBottom: 12 }}>{item.step}</div>
              <h3 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 8px' }}>{item.title}</h3>
              <p style={{ fontSize: 14, color: '#666', lineHeight: 1.5, margin: 0 }}>{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Forms supported */}
      <section style={{ maxWidth: 800, margin: '0 auto', padding: '40px 20px' }}>
        <h2 style={{ textAlign: 'center', fontSize: 24, fontWeight: 700, marginBottom: 8 }}>30+ Forms Supported</h2>
        <p style={{ textAlign: 'center', color: '#666', marginBottom: 32, fontSize: 14 }}>And growing. We can fill any government form with fields.</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
          {['Ration Card', 'PAN Card', 'Voter ID', 'Pension (Old Age)', 'Pension (Widow)', 'Pension (Disability)',
            'Ayushman Bharat', 'PM-KISAN', 'Kisan Credit Card', 'Jan Dhan Account',
            'Caste Certificate', 'Birth Certificate', 'MNREGA Job Card', 'PM Awas Yojana',
            'Driving Licence', 'Passport', 'Income Certificate', 'Domicile Certificate',
            'EWS Certificate', 'Disability Certificate', 'Sukanya Samriddhi', 'PPF Account',
          ].map(f => (
            <span key={f} style={{ background: '#f0fdf4', color: '#065f46', padding: '6px 14px', borderRadius: 20, fontSize: 13, fontWeight: 500, border: '1px solid #bbf7d0' }}>{f}</span>
          ))}
        </div>
      </section>

      {/* Languages */}
      <section style={{ maxWidth: 800, margin: '0 auto', padding: '40px 20px', textAlign: 'center' }}>
        <h2 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>Speak your language</h2>
        <p style={{ color: '#666', marginBottom: 24, fontSize: 14 }}>Voice notes and text in any Indian language</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
          {['हिन्दी Hindi', 'বাংলা Bengali', 'தமிழ் Tamil', 'తెలుగు Telugu', 'मराठी Marathi', 'ગુજરાતી Gujarati',
            'ಕನ್ನಡ Kannada', 'മലയാളം Malayalam', 'ਪੰਜਾਬੀ Punjabi', 'اردو Urdu', 'English'].map(l => (
            <span key={l} style={{ background: '#f5f5f5', padding: '6px 14px', borderRadius: 20, fontSize: 13, border: '1px solid #e5e5e5' }}>{l}</span>
          ))}
        </div>
      </section>

      {/* For village workers */}
      <section style={{ maxWidth: 800, margin: '0 auto', padding: '40px 20px', background: '#f0fdf4', borderRadius: 16, textAlign: 'center' }}>
        <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>For Gram Panchayats & CSC Centers</h2>
        <p style={{ color: '#065f46', fontSize: 15, maxWidth: 500, margin: '0 auto 20px', lineHeight: 1.6 }}>
          GramSetu can be deployed at Common Service Centers (CSCs) and Gram Panchayats.
          One WhatsApp number serves the entire village. No computers needed — just a phone.
        </p>
        {whatsappLink ? (
          <a href={whatsappLink} target="_blank" rel="noopener noreferrer"
            style={{ display: 'inline-block', background: '#059669', color: '#fff', padding: '12px 28px', borderRadius: 100, textDecoration: 'none', fontWeight: 600 }}>
            Start Serving Your Village →
          </a>
        ) : null}
      </section>

      {/* Footer */}
      <footer style={{ padding: '40px 20px', textAlign: 'center', fontSize: 13, color: '#999', borderTop: '1px solid #eee' }}>
        <p>GramSetu — AI-powered government services for rural India.</p>
        <p style={{ marginTop: 4 }}>Open source. Free forever. <a href="https://github.com/Vickyrrrrrr/gramsetu" style={{ color: '#059669' }}>GitHub</a></p>
      </footer>
    </main>
  )
}
