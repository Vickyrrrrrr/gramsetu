'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowLeft, Send, Loader2, ChevronRight, X, Mic, MicOff,
  Activity, RefreshCw, Globe, Image as ImageIcon, Wifi, WifiOff,
  Minimize2, Maximize2, Monitor,
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════
   TYPES
   ═══════════════════════════════════════════════════════════════ */

type Role = 'user' | 'assistant' | 'system'

interface Message {
  id: string
  role: Role
  text: string
  screenshotUrl?: string | null
  digilockerStatus?: string | null
  receiptUrl?: string | null
}

type Status = 'idle' | 'loading' | 'error'

interface McpServer {
  name: string
  port: number
  online: boolean
  lastPing: string
}

interface SchemeCard {
  id: string
  name: string
  benefit: string
  emoji: string
}

/* ═══════════════════════════════════════════════════════════════
   CONSTANTS
   ═══════════════════════════════════════════════════════════════ */

const QUICK_ACTIONS = [
  { label: 'Ration Card', prompt: 'I need to apply for a ration card' },
  { label: 'PM-KISAN', prompt: 'How do I register for PM-KISAN?' },
  { label: 'Ayushman Bharat', prompt: 'Apply for Ayushman Bharat health card' },
  { label: 'Voter ID', prompt: 'New voter ID card application' },
  { label: 'PAN Card', prompt: 'Apply for PAN card' },
  { label: 'Old Age Pension', prompt: 'Apply for old age pension' },
]

const INITIAL_MSG: Message = {
  id: 'init',
  role: 'assistant',
  text:
    'Hello! I\'m GramSetu, your AI assistant for government services.\n\n' +
    'I can help you:\n' +
    '• Apply for Ration Card, PAN, Voter ID, Ayushman Bharat, PM-KISAN, Pension & more\n' +
    '• Answer questions about any government scheme\n' +
    '• Explain eligibility, documents needed, and the full process\n\n' +
    'Type in Hindi, English, or any Indian language — I understand all of them.\n\n' +
    'What would you like help with today?',
}

const LANG_MAP: Record<string, { flag: string; name: string }> = {
  hi: { flag: '🇮🇳', name: 'Hindi' },
  en: { flag: '🇬🇧', name: 'English' },
  bn: { flag: '🇮🇳', name: 'Bengali' },
  te: { flag: '🇮🇳', name: 'Telugu' },
  ta: { flag: '🇮🇳', name: 'Tamil' },
  mr: { flag: '🇮🇳', name: 'Marathi' },
  gu: { flag: '🇮🇳', name: 'Gujarati' },
  kn: { flag: '🇮🇳', name: 'Kannada' },
  ml: { flag: '🇮🇳', name: 'Malayalam' },
  pa: { flag: '🇮🇳', name: 'Punjabi' },
  ur: { flag: '🇵🇰', name: 'Urdu' },
}

const MAX_STORED_MSGS = 50

function SafetyBanner() {
  const checks = [
    'Every field is normalized before validation',
    'Low-confidence AI extraction forces human review',
    'Missing required fields block submission',
    'Cross-field mismatches are flagged before automation',
    'Live browser fill uses a dry-run plan first',
  ]

  return (
    <section className="mb-6 rounded-3xl border border-emerald-200/70 bg-emerald-50 px-5 py-4 text-sm text-emerald-950 shadow-sm">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-emerald-700">Reliability mode</p>
          <h2 className="mt-1 text-lg font-semibold">Submission is blocked until safety checks pass.</h2>
          <p className="mt-1 max-w-2xl text-emerald-900/80">
            GramSetu v2 now validates risky fields, highlights contradictions, and asks for review before it touches a live government portal.
          </p>
        </div>
        <div className="rounded-2xl border border-emerald-300/70 bg-white/80 px-3 py-2 text-xs font-medium text-emerald-800">
          Dry-run first · Human review for risky flows
        </div>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {checks.map((item) => (
          <div key={item} className="rounded-2xl border border-emerald-200/80 bg-white px-3 py-2 text-[13px] text-emerald-950/85">
            {item}
          </div>
        ))}
      </div>
    </section>
  )
}


/* ═══════════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════════ */

function uid() {
  return Math.random().toString(36).slice(2)
}

function TypingDots() {
  return (
    <div className="flex gap-1 items-center px-3 py-2">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="inline-block w-1.5 h-1.5 rounded-full typing-dot"
          style={{ background: '#6B6B6B', animationDelay: `${i * 0.2}s` }}
        />
      ))}
    </div>
  )
}

function BubbleText({ text }: { text: string }) {
  return (
    <div className="space-y-1">
      {text.split('\n').map((line, i) => (
        <p
          key={i}
          dangerouslySetInnerHTML={{
            __html:
              line
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.+?)\*/g, '<em>$1</em>') || '&nbsp;',
          }}
        />
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   MOBILE MODAL
   ═══════════════════════════════════════════════════════════════ */

function MobileModal({
  onSubmit,
  onClose,
}: {
  onSubmit: (n: string) => void
  onClose: () => void
}) {
  const [val, setVal] = useState('')
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,.35)' }}
    >
      <div
        className="w-full max-w-sm mx-4 rounded-2xl p-6"
        style={{ background: 'white', border: '1px solid #E5E5E0' }}
      >
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="font-semibold text-base">Your mobile number</h3>
            <p className="text-sm mt-1" style={{ color: '#6B6B6B' }}>
              GramSetu uses this to link your Aadhaar and DigiLocker for auto
              form-filling.
            </p>
          </div>
          <button onClick={onClose} style={{ color: '#6B6B6B' }}>
            <X size={16} />
          </button>
        </div>
        <div className="flex gap-2 mb-3">
          <span
            className="flex items-center px-3 rounded-lg text-sm"
            style={{ border: '1px solid #E5E5E0', color: '#6B6B6B' }}
          >
            +91
          </span>
          <input
            autoFocus
            type="tel"
            maxLength={10}
            placeholder="98765 43210"
            value={val}
            onChange={(e) => setVal(e.target.value.replace(/\D/g, ''))}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && val.length === 10) onSubmit('+91' + val)
            }}
            className="flex-1 px-3 py-2.5 rounded-lg text-sm outline-none"
            style={{ border: '1px solid #E5E5E0' }}
          />
        </div>
        <button
          disabled={val.length !== 10}
          onClick={() => onSubmit('+91' + val)}
          className="w-full py-2.5 rounded-lg text-sm font-medium disabled:opacity-40 transition-opacity"
          style={{ background: '#0C0C0C', color: '#F7F6F3' }}
        >
          Continue
        </button>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   SCREENSHOT MODAL
   ═══════════════════════════════════════════════════════════════ */

function ScreenshotModal({
  url,
  onClose,
}: {
  url: string
  onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,.7)' }}
      onClick={onClose}
    >
      <div className="relative max-w-4xl w-full" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-white hover:text-gray-300"
        >
          <X size={24} />
        </button>
        <img
          src={url}
          alt="Form screenshot"
          className="w-full rounded-lg shadow-2xl"
        />
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   MCP STATUS PANEL
   ═══════════════════════════════════════════════════════════════ */

function McpPanel({
  servers,
  open,
  onClose,
}: {
  servers: McpServer[]
  open: boolean
  onClose: () => void
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className="fixed top-0 right-0 bottom-0 w-72 z-40 shadow-xl flex flex-col"
          style={{ background: '#F7F6F3', borderLeft: '1px solid #E5E5E0' }}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b"
            style={{ borderColor: '#E5E5E0' }}>
            <h3 className="font-semibold text-sm flex items-center gap-2">
              <Activity size={14} /> Live Systems
            </h3>
            <button onClick={onClose} style={{ color: '#6B6B6B' }}>
              <X size={16} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {servers.map((s) => (
              <div
                key={s.name}
                className="p-3 rounded-lg"
                style={{ background: 'white', border: '1px solid #E5E5E0' }}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ background: s.online ? '#22c55e' : '#ef4444' }}
                  />
                  <span className="text-sm font-medium">{s.name}</span>
                </div>
                <div className="flex justify-between mt-1.5">
                  <span className="text-xs" style={{ color: '#6B6B6B' }}>
                    Port {s.port}
                  </span>
                  <span className="text-xs" style={{ color: '#6B6B6B' }}>
                    {s.online ? s.lastPing : 'Offline'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/* ═══════════════════════════════════════════════════════════════
   SCHEME DISCOVERY PANEL
   ═══════════════════════════════════════════════════════════════ */

function SchemePanel({
  schemes,
  onSelect,
}: {
  schemes: SchemeCard[]
  onSelect: (name: string) => void
}) {
  if (schemes.length === 0) return null
  return (
    <div className="px-4 py-3" style={{ borderTop: '1px solid #E5E5E0' }}>
      <p className="text-xs font-medium mb-2" style={{ color: '#6B6B6B' }}>
        Schemes for You
      </p>
      <div className="flex gap-2 overflow-x-auto pb-2">
        {schemes.slice(0, 6).map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s.name)}
            className="flex-shrink-0 p-3 rounded-lg text-left transition-shadow hover:shadow-md"
            style={{
              background: 'white',
              border: '1px solid #E5E5E0',
              width: 160,
            }}
          >
            <span className="text-lg">{s.emoji}</span>
            <p className="text-xs font-semibold mt-1 line-clamp-2">{s.name}</p>
            {s.benefit && (
              <p
                className="text-xs mt-0.5 line-clamp-1"
                style={{ color: '#6B6B6B' }}
              >
                {s.benefit}
              </p>
            )}
            <span
              className="inline-block mt-1.5 text-xs font-medium"
              style={{ color: '#0C0C0C' }}
            >
              Apply Now →
            </span>
          </button>
        ))}
        <button
          onClick={() => onSelect('What schemes am I eligible for?')}
          className="flex-shrink-0 flex items-center justify-center p-3 rounded-lg text-xs font-medium"
          style={{
            border: '1px dashed #E5E5E0',
            color: '#6B6B6B',
            width: 120,
          }}
        >
          Discover more →
        </button>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   LANGUAGE BADGE
   ═══════════════════════════════════════════════════════════════ */

function LanguageBadge({
  langCode,
  onPick,
}: {
  langCode: string
  onPick: (code: string) => void
}) {
  const [open, setOpen] = useState(false)
  const info = LANG_MAP[langCode] || LANG_MAP.hi
  return (
    <div className="relative">
      <motion.button
        key={langCode}
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        onClick={() => setOpen(!open)}
        className="text-xs px-2.5 py-1 rounded-full flex items-center gap-1"
        style={{ border: '1px solid #E5E5E0', color: '#6B6B6B' }}
      >
        <Globe size={11} /> {info.flag} {info.name}
      </motion.button>
      {open && (
        <div
          className="absolute right-0 top-8 z-30 rounded-lg shadow-lg py-1 max-h-60 overflow-y-auto"
          style={{
            background: 'white',
            border: '1px solid #E5E5E0',
            width: 150,
          }}
        >
          {Object.entries(LANG_MAP).map(([code, { flag, name }]) => (
            <button
              key={code}
              onClick={() => {
                onPick(code)
                setOpen(false)
              }}
              className="w-full text-left text-xs px-3 py-1.5 hover:bg-gray-50 flex items-center gap-2"
            >
              {flag} {name}
              {code === langCode && <span className="ml-auto text-green-600">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   BROWSER PREVIEW
   ═══════════════════════════════════════════════════════════════ */

function BrowserPreview({
  frame,
  step,
  progress,
  minimized,
  onMinimize,
  onMaximize,
  onClose,
}: {
  frame: string | null
  step: string
  progress: number
  minimized: boolean
  onMinimize: () => void
  onMaximize: () => void
  onClose: () => void
}) {
  if (!frame) return null

  /* minimized pill */
  if (minimized) {
    return (
      <motion.button
        layout
        initial={{ scale: 0.6, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.6, opacity: 0 }}
        transition={{ type: 'spring', damping: 22, stiffness: 300 }}
        onClick={onMaximize}
        className="fixed bottom-20 right-4 z-50 w-12 h-12 rounded-full shadow-lg flex items-center justify-center"
        style={{ background: '#0C0C0C', color: '#F7F6F3' }}
        title="Show browser preview"
      >
        <Monitor size={18} />
        {/* progress ring */}
        <svg className="absolute inset-0 w-12 h-12 -rotate-90" viewBox="0 0 48 48">
          <circle cx="24" cy="24" r="20" fill="none" stroke="#E5E5E0" strokeWidth="3" />
          <circle
            cx="24" cy="24" r="20" fill="none" stroke="#22c55e" strokeWidth="3"
            strokeDasharray={`${125.6 * progress} 125.6`}
            strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.4s ease' }}
          />
        </svg>
      </motion.button>
    )
  }

  /* expanded panel */
  return (
    <motion.div
      layout
      initial={{ y: 60, opacity: 0, scale: 0.92 }}
      animate={{ y: 0, opacity: 1, scale: 1 }}
      exit={{ y: 60, opacity: 0, scale: 0.92 }}
      transition={{ type: 'spring', damping: 25, stiffness: 280 }}
      className="fixed bottom-20 right-4 z-50 w-[380px] rounded-xl shadow-2xl overflow-hidden"
      style={{ background: 'white', border: '1px solid #E5E5E0' }}
    >
      {/* header */}
      <div
        className="flex items-center justify-between px-3 py-2"
        style={{ background: '#0C0C0C', color: '#F7F6F3' }}
      >
        <span className="text-xs font-medium flex items-center gap-1.5">
          <Monitor size={12} /> Live Form Filling
        </span>
        <div className="flex items-center gap-1">
          <button onClick={onMinimize} className="p-1 rounded hover:bg-white/10 transition-colors">
            <Minimize2 size={12} />
          </button>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/10 transition-colors">
            <X size={12} />
          </button>
        </div>
      </div>

      {/* screenshot */}
      <img
        src={`data:image/jpeg;base64,${frame}`}
        alt="Browser preview"
        className="w-full"
        style={{ maxHeight: 280, objectFit: 'cover', objectPosition: 'top' }}
      />

      {/* progress footer */}
      <div className="px-3 py-2" style={{ borderTop: '1px solid #E5E5E0' }}>
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs font-medium truncate" style={{ color: '#0C0C0C', maxWidth: '80%' }}>
            {step || 'Filling form…'}
          </p>
          <span className="text-xs tabular-nums" style={{ color: '#6B6B6B' }}>
            {Math.round(progress * 100)}%
          </span>
        </div>
        <div className="w-full h-1.5 rounded-full" style={{ background: '#E5E5E0' }}>
          <motion.div
            className="h-full rounded-full"
            style={{ background: '#22c55e' }}
            initial={{ width: 0 }}
            animate={{ width: `${progress * 100}%` }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
          />
        </div>
      </div>
    </motion.div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════════════════════ */

export default function AppPage() {
  /* ── session persistence helpers ───────────────────────────── */
  function loadSession() {
    if (typeof window === 'undefined') return null
    try {
      const raw = localStorage.getItem('gramsetu_session')
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  }
  function loadMessages(id: string): Message[] | null {
    if (typeof window === 'undefined') return null
    try {
      const raw = localStorage.getItem(`gramsetu_chat_${id}`)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  }

  /* ── state ─────────────────────────────────────────────────── */
  const saved = loadSession()
  const [messages, setMessages] = useState<Message[]>(() => {
    if (saved) {
      const m = loadMessages(saved.userId)
      if (m && m.length > 0) return m
    }
    return [INITIAL_MSG]
  })
  const [input, setInput] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [userId] = useState(() => saved?.userId ?? 'web-' + uid())
  const [phone, setPhone] = useState(saved?.phone ?? '')
  const [showMobileModal, setShowMobileModal] = useState(false)
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null)
  const [language, setLanguage] = useState(saved?.language ?? 'hi')
  const [langOverride, setLangOverride] = useState<string | null>(null)

  // MCP panel
  const [mcpOpen, setMcpOpen] = useState(false)
  const [mcpServers, setMcpServers] = useState<McpServer[]>([
    { name: 'WhatsApp MCP', port: 8100, online: false, lastPing: '' },
    { name: 'Browser MCP', port: 8101, online: false, lastPing: '' },
    { name: 'Audit MCP', port: 8102, online: false, lastPing: '' },
    { name: 'DigiLocker MCP', port: 8103, online: false, lastPing: '' },
  ])
  const [mcpWarning, setMcpWarning] = useState('')

  // Screenshot modal
  const [screenshotModal, setScreenshotModal] = useState<string | null>(null)

  // Voice recording
  const [recording, setRecording] = useState(false)
  const [voiceSupported, setVoiceSupported] = useState(true)
  const mediaRecRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  // Schemes
  const [schemes, setSchemes] = useState<SchemeCard[]>([])

  // Browser live preview
  const [browserFrame, setBrowserFrame] = useState<string | null>(null)
  const [browserStep, setBrowserStep] = useState('')
  const [browserProgress, setBrowserProgress] = useState(0)
  const [browserMinimized, setBrowserMinimized] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  /* ── persist to localStorage ───────────────────────────────── */
  useEffect(() => {
    if (typeof window === 'undefined') return
    localStorage.setItem(
      'gramsetu_session',
      JSON.stringify({ userId, phone, language })
    )
  }, [userId, phone, language])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const capped = messages.slice(-MAX_STORED_MSGS)
    localStorage.setItem(`gramsetu_chat_${userId}`, JSON.stringify(capped))
  }, [messages, userId])

  /* ── scroll to bottom ──────────────────────────────────────── */
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages, status])

  /* ── MCP status — on-demand only (when panel opened) ────── */
  useEffect(() => {
    if (!mcpOpen) return
    let cancelled = false
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/mcp-status')
        if (!res.ok || cancelled) return
        const data = await res.json()
        const now = new Date().toLocaleTimeString()
        setMcpServers([
          { name: 'WhatsApp MCP', port: 8100, online: !!data.whatsapp, lastPing: now },
          { name: 'Browser MCP', port: 8101, online: !!data.browser, lastPing: now },
          { name: 'Audit MCP', port: 8102, online: !!data.audit, lastPing: now },
          { name: 'DigiLocker MCP', port: 8103, online: !!data.digilocker, lastPing: now },
        ])
        const offline = []
        if (!data.whatsapp) offline.push('WhatsApp')
        if (!data.digilocker) offline.push('DigiLocker')
        if (!data.browser) offline.push('Browser')
        setMcpWarning(
          offline.length > 0
            ? `⚠️ ${offline.join(', ')} service unavailable — some features may be slower`
            : ''
        )
      } catch {
        // backend down
      }
    }
    fetchStatus()
    return () => { cancelled = true }
  }, [mcpOpen])

  /* ── Browser preview WebSocket — always-on with auto-reconnect ── */
  useEffect(() => {
    const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const apiEnv = process.env.NEXT_PUBLIC_API_URL || ''
    const backendHost = apiEnv ? apiEnv.replace(/^https?:\/\//, '') : window.location.host
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let alive = true

    const connect = () => {
      if (!alive) return
      try {
        ws = new WebSocket(`${wsProto}://${backendHost}/ws/browser/${userId}`)
      } catch { return }
      wsRef.current = ws

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.type === 'browser_frame') {
            setBrowserFrame(msg.screenshot)
            setBrowserStep(msg.step || '')
            setBrowserProgress(msg.progress ?? 0)
          }
        } catch { /* ignore non-json */ }
      }

      ws.onclose = () => {
        wsRef.current = null
        // Reconnect after 3 s — keeps the channel ready for the next form-fill
        if (alive) reconnectTimer = setTimeout(connect, 3000)
      }

      ws.onerror = () => { ws?.close() }
    }

    connect()

    return () => {
      alive = false
      if (reconnectTimer) clearTimeout(reconnectTimer)
      ws?.close()
      wsRef.current = null
    }
  }, [userId])

  /* ── scheme discovery ──────────────────────────────────────── */
  useEffect(() => {
    const fetchSchemes = async () => {
      try {
        const res = await fetch('/api/schemes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'show all schemes', language: 'hi' }),
        })
        if (!res.ok) return
        const data = await res.json()
        if (data.schemes) setSchemes(data.schemes)
      } catch {
        // silent
      }
    }
    fetchSchemes()
  }, [])

  /* ── check voice support ───────────────────────────────────── */
  useEffect(() => {
    if (typeof window !== 'undefined' && !navigator.mediaDevices?.getUserMedia) {
      setVoiceSupported(false)
    }
  }, [])

  /* ── add message helper ────────────────────────────────────── */
  const addMsg = useCallback(
    (role: Role, text: string, extra?: Partial<Message>) => {
      setMessages((prev) => [
        ...prev,
        { id: uid(), role, text, ...extra },
      ])
    },
    []
  )

  /* ── call backend ──────────────────────────────────────────── */
  const callBackend = useCallback(
    async (text: string, phoneOverride?: string) => {
      setStatus('loading')
      const phoneToUse = phoneOverride ?? phone
      try {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (langOverride) headers['X-Language'] = langOverride

        const res = await fetch('/api/chat', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            message: text,
            user_id: userId,
            phone: phoneToUse || '9999999999',
            language: langOverride || undefined,
          }),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()

        // Update detected language
        if (data.language && LANG_MAP[data.language]) {
          setLanguage(data.language)
        }

        addMsg('assistant', data.response || 'Something went wrong.', {
          screenshotUrl: data.screenshot_url || null,
          digilockerStatus: data.digilocker_auth_status || null,
          receiptUrl: data.receipt_url || null,
        })
      } catch {
        addMsg(
          'system',
          'Could not reach the backend. Make sure the server is running on port 8000.'
        )
      } finally {
        setStatus('idle')
        setTimeout(() => inputRef.current?.focus(), 100)
      }
    },
    [phone, userId, addMsg, langOverride]
  )

  /* ── send message ──────────────────────────────────────────── */
  const handleSend = useCallback(
    (override?: string) => {
      const msg = (override ?? input).trim()
      if (!msg || status === 'loading') return
      setInput('')
      addMsg('user', msg)

      const isFormRequest =
        /form|apply|card|ration|pan|voter|pension|kisan|ayush|mnrega|jan dhan|birth|caste/i.test(
          msg
        )
      if (isFormRequest && !phone) {
        setPendingPrompt(msg)
        setShowMobileModal(true)
        return
      }
      callBackend(msg)
    },
    [input, status, phone, addMsg, callBackend]
  )

  /* ── mobile modal handlers ─────────────────────────────────── */
  const handleMobileSubmit = useCallback(
    (num: string) => {
      setPhone(num)
      setShowMobileModal(false)
      addMsg('system', `Mobile number saved: ${num.replace('+91', '+91 ')}`)
      if (pendingPrompt) {
        callBackend(pendingPrompt, num)
        setPendingPrompt(null)
      }
    },
    [pendingPrompt, addMsg, callBackend]
  )

  const handleMobileClose = useCallback(() => {
    setShowMobileModal(false)
    if (pendingPrompt) {
      callBackend(pendingPrompt)
      setPendingPrompt(null)
    }
  }, [pendingPrompt, callBackend])

  /* ── voice recording ───────────────────────────────────────── */
  const startRecording = useCallback(async () => {
    if (!voiceSupported) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      chunksRef.current = []
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        const fd = new FormData()
        fd.append('audio', blob, 'recording.webm')
        try {
          const res = await fetch('/api/voice', { method: 'POST', body: fd })
          if (!res.ok) throw new Error('Voice API error')
          const data = await res.json()
          if (data.text) {
            setInput(data.text)
            const timer = setTimeout(() => {
              handleSend(data.text)
            }, 1000)
            const cancelHandler = (e: KeyboardEvent) => {
              if (e.key === 'Escape') {
                clearTimeout(timer)
                window.removeEventListener('keydown', cancelHandler)
              }
            }
            window.addEventListener('keydown', cancelHandler)
          }
        } catch {
          // voice not available
        }
      }
      mr.start()
      mediaRecRef.current = mr
      setRecording(true)
    } catch {
      setVoiceSupported(false)
    }
  }, [voiceSupported, handleSend])

  const stopRecording = useCallback(() => {
    if (mediaRecRef.current && mediaRecRef.current.state !== 'inactive') {
      mediaRecRef.current.stop()
    }
    setRecording(false)
  }, [])

  /* ── new conversation ──────────────────────────────────────── */
  const handleNewConversation = useCallback(() => {
    localStorage.removeItem(`gramsetu_chat_${userId}`)
    localStorage.removeItem('gramsetu_session')
    setMessages([INITIAL_MSG])
    setInput('')
    setSchemes([])
  }, [userId])

  /* ── derived ───────────────────────────────────────────────── */
  const isFirstInteraction = messages.length <= 1

  /* ═══════════════════════════════════════════════════════════════
     RENDER
     ═══════════════════════════════════════════════════════════════ */
  return (
    <div className="flex flex-col h-screen" style={{ background: '#F7F6F3' }}>
      {/* ── Top bar ──────────────────────────────────────────── */}
      <header
        className="flex-shrink-0 flex items-center justify-between px-4 py-3"
        style={{ background: 'white', borderBottom: '1px solid #E5E5E0' }}
      >
        <div className="flex items-center gap-3">
          <Link href="/" style={{ color: '#6B6B6B' }}>
            <ArrowLeft size={18} />
          </Link>
          <div>
            <p className="font-semibold text-sm leading-tight">GramSetu</p>
            <p className="text-xs" style={{ color: '#6B6B6B' }}>
              {status === 'loading' ? 'Thinking…' : 'AI · Government Services'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Language badge (Upgrade 7) */}
          <LanguageBadge
            langCode={language}
            onPick={(code) => {
              setLangOverride(code)
              setLanguage(code)
            }}
          />

          {/* New conversation button (Upgrade 5) */}
          <button
            onClick={handleNewConversation}
            className="text-xs px-2.5 py-1 rounded-full transition-colors"
            style={{ border: '1px solid #E5E5E0', color: '#6B6B6B' }}
            title="New conversation"
          >
            <RefreshCw size={12} />
          </button>

          {/* Phone button */}
          <button
            onClick={() => setShowMobileModal(true)}
            className="text-xs px-3 py-1 rounded-full transition-colors"
            style={{ border: '1px solid #E5E5E0', color: '#6B6B6B' }}
          >
            {phone ? `+91 ···${phone.slice(-4)}` : '+ Add mobile'}
          </button>
        </div>
      </header>

      {/* ── Messages ─────────────────────────────────────────── */}
      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.map((m) =>
          m.role === 'system' ? (
            <div key={m.id} className="flex justify-center fade-up">
              <div
                className="text-xs px-3 py-1.5 rounded-full"
                style={{ background: '#E8D9C0', color: '#5D4037' }}
              >
                {m.text}
              </div>
            </div>
          ) : (
            <div
              key={m.id}
              className={`flex fade-up ${m.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
            >
              <div
                className={`max-w-[82%] px-4 py-3 text-sm leading-relaxed ${m.role === 'user' ? 'msg-user' : 'msg-ai'
                  }`}
              >
                {/* DigiLocker badge (Upgrade 8) */}
                {m.digilockerStatus === 'demo_connected' && (
                  <div className="flex items-center gap-1 text-xs font-medium text-green-700 mb-2">
                    🔒 DigiLocker Verified
                  </div>
                )}

                <BubbleText text={m.text} />

                {/* Receipt download button */}
                {m.receiptUrl && (
                  <div className="mt-3">
                    <a
                      href={m.receiptUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white"
                      style={{ background: '#16a34a' }}
                    >
                      📄 Download Receipt / Save as PDF
                    </a>
                    <p className="text-xs mt-1.5" style={{ color: '#6B6B6B' }}>
                      Opens a printable receipt — press Ctrl+P to save as PDF.
                    </p>
                  </div>
                )}

                {/* Screenshot viewer (Upgrade 2) */}
                {m.screenshotUrl && (
                  <div className="mt-3">
                    <button
                      onClick={() => setScreenshotModal(m.screenshotUrl!)}
                      className="block rounded-lg overflow-hidden shadow-md hover:shadow-lg transition-shadow cursor-pointer"
                      style={{ border: '1px solid #E5E5E0' }}
                    >
                      <img
                        src={m.screenshotUrl}
                        alt="Form filled"
                        className="w-full max-w-xs rounded-lg"
                        onError={(e) => {
                          // Hide broken image (old file-based URLs that 404)
                          (e.target as HTMLImageElement).style.display = 'none'
                        }}
                      />
                    </button>
                    <p
                      className="text-xs mt-1.5 flex items-center gap-1"
                      style={{ color: '#6B6B6B' }}
                    >
                      <ImageIcon size={10} /> Portal filled automatically —
                      browser screenshot
                    </p>
                  </div>
                )}
              </div>
            </div>
          )
        )}

        {status === 'loading' && (
          <div className="flex justify-start fade-up">
            <div className="msg-ai">
              <TypingDots />
            </div>
          </div>
        )}
      </div>

      {/* ── Scheme discovery (Upgrade 4) — only before first send */}
      {isFirstInteraction && status !== 'loading' && schemes.length > 0 && (
        <SchemePanel
          schemes={schemes}
          onSelect={(name) => handleSend(`I want to apply for ${name}`)}
        />
      )}

      {/* ── Quick-action chips ───────────────────────────────── */}
      {isFirstInteraction && status !== 'loading' && (
        <div
          className="flex-shrink-0 px-4 py-2 flex gap-2 overflow-x-auto"
          style={{ background: 'white', borderTop: '1px solid #E5E5E0' }}
        >
          {QUICK_ACTIONS.map((a) => (
            <button
              key={a.label}
              onClick={() => handleSend(a.prompt)}
              className="flex-shrink-0 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full whitespace-nowrap transition-colors hover:border-[#0C0C0C]"
              style={{ border: '1px solid #E5E5E0', color: '#0C0C0C' }}
            >
              {a.label} <ChevronRight size={10} />
            </button>
          ))}
        </div>
      )}

      {/* ── MCP warning (Upgrade 1) ──────────────────────────── */}
      {mcpWarning && (
        <div
          className="flex-shrink-0 px-4 py-1.5 text-xs flex items-center gap-1.5"
          style={{ background: '#fffbe6', color: '#b45309', borderTop: '1px solid #fde68a' }}
        >
          <WifiOff size={11} /> {mcpWarning}
        </div>
      )}

      {/* ── Recording indicator (Upgrade 3) ──────────────────── */}
      {recording && (
        <div
          className="flex-shrink-0 px-4 py-1.5 text-xs font-medium flex items-center gap-2"
          style={{ background: '#fee2e2', color: '#dc2626', borderTop: '1px solid #fecaca' }}
        >
          <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" />
          Recording… click mic again to stop
        </div>
      )}

      {/* ── Input bar ────────────────────────────────────────── */}
      <div
        className="flex-shrink-0 px-4 py-3 flex gap-2 items-end"
        style={{ borderTop: '1px solid #E5E5E0', background: 'white' }}
      >
        <textarea
          ref={inputRef}
          rows={1}
          value={input}
          placeholder="Ask anything in any language…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          className="flex-1 resize-none px-4 py-2.5 rounded-xl text-sm outline-none"
          style={{
            border: '1px solid #E5E5E0',
            background: '#F7F6F3',
            minHeight: 42,
            maxHeight: 120,
            lineHeight: '1.5',
          }}
        />

        {/* Mic button (Upgrade 3) */}
        {voiceSupported && (
          <button
            onClick={recording ? stopRecording : startRecording}
            className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-opacity"
            style={{
              background: recording ? '#dc2626' : '#0C0C0C',
              color: '#F7F6F3',
            }}
            title={recording ? 'Stop recording' : 'Voice input'}
          >
            {recording ? <MicOff size={15} /> : <Mic size={15} />}
          </button>
        )}

        {/* Send button */}
        <button
          onClick={() => handleSend()}
          disabled={!input.trim() || status === 'loading'}
          className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center disabled:opacity-40 transition-opacity"
          style={{ background: '#0C0C0C', color: '#F7F6F3' }}
        >
          {status === 'loading' ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Send size={15} />
          )}
        </button>

        {/* MCP panel toggle (Upgrade 1) */}
        <button
          onClick={() => setMcpOpen(!mcpOpen)}
          className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-opacity"
          style={{
            background: mcpWarning ? '#fef3c7' : '#f3f4f6',
            color: mcpWarning ? '#b45309' : '#6B6B6B',
          }}
          title="System status"
        >
          {mcpWarning ? <WifiOff size={14} /> : <Wifi size={14} />}
        </button>
      </div>

      {/* ── Modals & panels ──────────────────────────────────── */}
      {showMobileModal && (
        <MobileModal onSubmit={handleMobileSubmit} onClose={handleMobileClose} />
      )}

      {screenshotModal && (
        <ScreenshotModal
          url={screenshotModal}
          onClose={() => setScreenshotModal(null)}
        />
      )}

      <McpPanel
        servers={mcpServers}
        open={mcpOpen}
        onClose={() => setMcpOpen(false)}
      />

      {/* Live browser preview (form-fill stream) */}
      <AnimatePresence>
        {browserFrame && (
          <BrowserPreview
            frame={browserFrame}
            step={browserStep}
            progress={browserProgress}
            minimized={browserMinimized}
            onMinimize={() => setBrowserMinimized(true)}
            onMaximize={() => setBrowserMinimized(false)}
            onClose={() => {
              setBrowserFrame(null)
              setBrowserStep('')
              setBrowserProgress(0)
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
