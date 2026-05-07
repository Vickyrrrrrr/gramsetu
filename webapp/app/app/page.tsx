'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { Send, Loader2, X, Mic, MicOff, Activity, RefreshCw, Globe, Monitor, Volume2, Database, Wifi, WifiOff, Camera, User, FileImage } from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════
   TYPES
   ═══════════════════════════════════════════════════════════════ */

type Role = 'user' | 'assistant' | 'system'
interface Message { id: string; role: Role; text: string; screenshotUrl?: string | null; receiptUrl?: string | null }
interface McpServer { name: string; port: number; online: boolean; lastPing: string }
interface SchemeCard { id: string; name: string; emoji: string }
type Status = 'idle' | 'loading' | 'error'

/* ═══════════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════════ */

function uid() { return Math.random().toString(36).slice(2) }

const LANG_MAP: Record<string, string> = {
  hi: 'हिन्दी', en: 'English', bn: 'বাংলা', te: 'తెలుగు', ta: 'தமிழ்',
  mr: 'मराठी', gu: 'ગુજરાતી', kn: 'ಕನ್ನಡ', ml: 'മലയാളം', pa: 'ਪੰਜਾਬੀ', ur: 'اردو',
}

const INITIAL_MSG: Message = {
  id: 'init', role: 'assistant',
  text: 'Namaste! I\'m GramSetu — your AI assistant.\n\nDo you want to fill a **Government Form** (like schemes or IDs) or a **Non-Government Form** (like private jobs, school applications)?',
}

const QUICK = [
  'Government Form', 'Non-Government Form', 'Ration Card', 'PM-KISAN'
]

/* ═══════════════════════════════════════════════════════════════
   PROGRESS ROW
   ═══════════════════════════════════════════════════════════════ */

function ProgressRow({ step, pct }: { step: string; pct: number }) {
  if (!step || pct === 0) return null
  return (
    <div
      className="mx-4 mb-2 px-3 py-1.5 rounded-lg flex items-center gap-2 text-xs"
      style={{
        background: 'var(--surface-strong)',
        color: 'var(--ink)',
        border: '1px solid var(--hairline)',
      }}
    >
      <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--success)' }} />
      <span>{step}</span>
      <span className="ml-auto tabular-nums" style={{ color: 'var(--muted)' }}>
        {Math.round(pct * 100)}%
      </span>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   BUBBLE TEXT
   ═══════════════════════════════════════════════════════════════ */

function Bubble({ text }: { text: string }) {
  return (
    <div className="space-y-0.5" suppressHydrationWarning>
      {text.split('\n').map((line, i) => (
        <p key={i} suppressHydrationWarning dangerouslySetInnerHTML={{
          __html: line
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>') || '&nbsp;'
        }} />
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   VAULT PANEL
   ═══════════════════════════════════════════════════════════════ */

function VaultPanel({ onClose, userId, onUseData }: {
  onClose: () => void; userId: string; onUseData: (d: Record<string, string>) => void
}) {
  const [pass, setPass] = useState('')
  const [items, setItems] = useState<{ id: string; label: string; value: string }[]>([])
  const [unlocked, setUnlocked] = useState(false)
  const [newLabel, setNewLabel] = useState('')
  const [newVal, setNewVal] = useState('')

  const load = async () => {
    try {
      const res = await fetch(`/api/vault/${userId}`)
      if (res.ok) {
        const data = await res.json()
        setItems(data.items || [])
      }
      setUnlocked(true)
    } catch { setItems([]); setUnlocked(true) }
  }

  const saveDataToBackend = async (newItems: typeof items) => {
    try {
      await fetch(`/api/vault/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: newItems })
      })
    } catch (e) { console.error('Vault save error', e) }
  }

  const save = async () => {
    if (!newLabel || !newVal) return
    const u = [...items, { id: uid(), label: newLabel, value: newVal }]
    setItems(u)
    await saveDataToBackend(u)
    setNewLabel(''); setNewVal('')
  }

  const remove = async (id: string) => {
    const u = items.filter(i => i.id !== id)
    setItems(u)
    await saveDataToBackend(u)
  }

  const useAll = () => {
    const d: Record<string, string> = {}
    items.forEach(i => { d[i.label.toLowerCase().replace(/\s+/g, '_')] = i.value })
    onUseData(d)
    onClose()
  }

  return (
    <div
      className="fixed right-0 top-0 bottom-0 w-72 z-50 shadow-xl flex flex-col text-sm"
      style={{ background: 'var(--surface-card)', borderLeft: '1px solid var(--hairline)' }}
    >
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: '1px solid var(--hairline)' }}
      >
        <span className="font-semibold" style={{ color: 'var(--ink)' }}>Your Data</span>
        <button onClick={onClose} className="p-1 opacity-50 hover:opacity-100">
          <X size={16} color="var(--ink)" />
        </button>
      </div>

      {!unlocked ? (
        <form onSubmit={(e) => { e.preventDefault(); load() }} className="flex-1 flex flex-col justify-center gap-3 px-5">
          <p className="text-xs text-center" style={{ color: 'var(--muted-soft)' }}>
            Enter your vault password
          </p>
          <input
            type="password"
            value={pass}
            onChange={e => setPass(e.target.value)}
            placeholder="Password"
            className="input-editorial w-full"
            style={{ height: 40 }}
          />
          <button type="submit" className="btn-primary w-full text-xs justify-center">
            Unlock
          </button>
        </form>
      ) : (
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {items.map(i => (
            <div
              key={i.id}
              className="p-2 rounded-lg group flex items-center justify-between"
              style={{ background: 'var(--canvas)' }}
            >
              <div className="min-w-0">
                <div
                  className="text-[10px] uppercase font-medium"
                  style={{ color: 'var(--muted-soft)' }}
                >
                  {i.label}
                </div>
                <div className="text-sm truncate" style={{ color: 'var(--ink)' }}>{i.value}</div>
              </div>
              <button
                onClick={() => remove(i.id)}
                className="opacity-0 group-hover:opacity-100 text-xs ml-2"
                style={{ color: 'var(--error)' }}
              >
                &times;
              </button>
            </div>
          ))}
          <div className="pt-3 space-y-2" style={{ borderTop: '1px solid var(--hairline)' }}>
            <input
              value={newLabel}
              onChange={e => setNewLabel(e.target.value)}
              placeholder="Label"
              className="input-editorial w-full text-xs"
              style={{ height: 36 }}
            />
            <input
              value={newVal}
              onChange={e => setNewVal(e.target.value)}
              placeholder="Value"
              className="input-editorial w-full text-xs"
              style={{ height: 36 }}
            />
            <button onClick={save} className="btn-primary w-full text-xs justify-center" style={{ height: 36 }}>
              Add
            </button>
          </div>
        </div>
      )}

      {unlocked && items.length > 0 && (
        <div className="p-4" style={{ borderTop: '1px solid var(--hairline)' }}>
          <button onClick={useAll} className="btn-primary w-full text-xs justify-center">
            Use This Data
          </button>
        </div>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   MCP PANEL
   ═══════════════════════════════════════════════════════════════ */

function McpPanel({ servers, open, onClose }: { servers: McpServer[]; open: boolean; onClose: () => void }) {
  if (!open) return null
  return (
    <div
      className="fixed right-0 top-0 bottom-0 w-60 z-40 shadow-lg flex flex-col text-sm"
      style={{ background: 'var(--surface-card)', borderLeft: '1px solid var(--hairline)' }}
    >
      <div
        className="flex items-center justify-between px-3 py-3"
        style={{ borderBottom: '1px solid var(--hairline)' }}
      >
        <span className="font-semibold text-xs flex items-center gap-1.5" style={{ color: 'var(--ink)' }}>
          <Activity size={12} /> Systems
        </span>
        <button onClick={onClose} className="opacity-50 hover:opacity-100">
          <X size={14} color="var(--ink)" />
        </button>
      </div>
      <div className="p-3 space-y-2">
        {servers.map(s => (
          <div
            key={s.name}
            className="p-2 rounded-lg text-xs"
            style={{ border: '1px solid var(--hairline)', background: 'var(--surface-card)' }}
          >
            <div className="flex items-center gap-1.5">
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: s.online ? 'var(--success)' : 'var(--error)' }}
              />
              <span className="font-medium" style={{ color: 'var(--ink)' }}>{s.name}</span>
            </div>
            <div className="mt-0.5" style={{ color: 'var(--muted-soft)' }}>
              :{s.port} &middot; {s.online ? s.lastPing : 'offline'}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════════════════════ */

export default function AppPage() {
  const [mounted, setMounted] = useState(false)
  const [messages, setMessages] = useState<Message[]>([INITIAL_MSG])
  const [input, setInput] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [userId, setUserId] = useState('u_' + uid())
  const [phone, setPhone] = useState('')
  const [lang, setLang] = useState('hi')

  useEffect(() => {
    setMounted(true)
    const savedRaw = localStorage.getItem('gs_s')
    if (savedRaw) {
      try {
        const saved = JSON.parse(savedRaw)
        if (saved.uid) setUserId(saved.uid)
        if (saved.phone) setPhone(saved.phone)
        if (saved.lang) setLang(saved.lang)
        const savedMsgs = localStorage.getItem(`gs_c_${saved.uid}`)
        if (savedMsgs) {
          const msgs = JSON.parse(savedMsgs)
          if (msgs.length) setMessages(msgs)
        }
      } catch (e) { console.error('Failed to load saved state', e) }
    }
  }, [])

  const [langOpen, setLangOpen] = useState(false)
  const [mcpOpen, setMcpOpen] = useState(false)
  const [mcpSrv, setMcpSrv] = useState<McpServer[]>([
    { name: 'Browser', port: 8101, online: false, lastPing: '' },
    { name: 'Audit', port: 8102, online: false, lastPing: '' },
    { name: 'DigiLocker', port: 8103, online: false, lastPing: '' },
    { name: 'WhatsApp', port: 8104, online: false, lastPing: '' },
  ])
  const [mcpWarn, setMcpWarn] = useState('')
  const [recording, setRecording] = useState(false)
  const [recordingTime, setRecordingTime] = useState(0)
  const [liveTxt, setLiveTxt] = useState('')
  const [errorBanner, setErrorBanner] = useState('')
  const [isOnline, setIsOnline] = useState(true)
  const [lastFailedMsg, setLastFailedMsg] = useState<string | null>(null)
  const recordingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [schemes, setSchemes] = useState<SchemeCard[]>([])
  const [browserFrame, setBrowserFrame] = useState<string | null>(null)
  const [browserStep, setBrowserStep] = useState('')
  const [browserPct, setBrowserPct] = useState(0)
  const [browserMin, setBrowserMin] = useState(false)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [vaultOpen, setVaultOpen] = useState(false)
  const [phoneModal, setPhoneModal] = useState(false)
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null)
  const [progressStep, setProgressStep] = useState('')
  const [progressPct, setProgressPct] = useState(0)
  const [screenshotModal, setScreenshotModal] = useState<string | null>(null)
  const [selfieOpen, setSelfieOpen] = useState(false)
  const [cameraError, setCameraError] = useState('')
  const [capturedSelfie, setCapturedSelfie] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const mediaRecRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  /* ── persist ───────────────────────── */
  useEffect(() => {
    if (typeof window === 'undefined') return
    localStorage.setItem('gs_s', JSON.stringify({ uid: userId, phone, lang }))
  }, [userId, phone, lang])

  /* ── online status ─────────────────── */
  useEffect(() => {
    const goOnline = () => setIsOnline(true)
    const goOffline = () => setIsOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  /* ── error auto-dismiss ────────────── */
  useEffect(() => {
    if (!errorBanner) return
    const t = setTimeout(() => setErrorBanner(''), 6000)
    return () => clearTimeout(t)
  }, [errorBanner])

  useEffect(() => {
    if (typeof window === 'undefined') return
    localStorage.setItem(`gs_c_${userId}`, JSON.stringify(messages.slice(-50)))
  }, [messages, userId])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, status])

  /* ── MCP status ────────────────────── */
  useEffect(() => {
    if (!mcpOpen) return
    let c = false
    const f = async () => {
      try {
        const r = await fetch('/api/mcp-status')
        if (!r.ok || c) return
        const d = await r.json()
        const n = new Date().toLocaleTimeString()
        setMcpSrv([
          { name: 'Browser', port: 8101, online: !!d.browser, lastPing: n },
          { name: 'Audit', port: 8102, online: !!d.audit, lastPing: n },
          { name: 'DigiLocker', port: 8103, online: !!d.digilocker, lastPing: n },
          { name: 'WhatsApp', port: 8104, online: !!d.whatsapp, lastPing: n },
        ])
        const off = []
        if (!d.digilocker) off.push('DigiLocker')
        if (!d.browser) off.push('Browser')
        setMcpWarn(off.length ? `${off.join(', ')} unavailable` : '')
      } catch {}
    }
    f()
    return () => { c = true }
  }, [mcpOpen])

  /* ── WebSocket (browser preview) ── */
  useEffect(() => {
    const isHttps = window.location.protocol === 'https:'
    if (isHttps) return
    const p = 'ws'
    let ws: WebSocket | null = null
    let rt: ReturnType<typeof setTimeout> | null = null
    let a = true
    const conn = () => {
      if (!a) return
      try { ws = new WebSocket(`${p}://${window.location.hostname}:8000/ws/browser/${userId}`) } catch { return }
      wsRef.current = ws
      ws.onmessage = ev => {
        try {
          const m = JSON.parse(ev.data)
          if (m.type === 'browser_frame') { setBrowserFrame(m.screenshot); setBrowserStep(m.step || ''); setBrowserPct(m.progress || 0) }
          else if (m.type === 'progress') { setProgressStep(m.step || ''); setProgressPct(m.progress || 0) }
        } catch {}
      }
      ws.onclose = () => { wsRef.current = null; if (a) rt = setTimeout(conn, 3000) }
      ws.onerror = () => ws?.close()
    }
    conn()
    return () => { a = false; if (rt) clearTimeout(rt); ws?.close(); wsRef.current = null }
  }, [userId])

  /* ── schemes ──────────────────────── */
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch('/api/schemes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'show', language: 'hi' }),
        })
        if (r.ok) { const d = await r.json(); if (d.schemes) setSchemes(d.schemes) }
      } catch {}
    })()
  }, [])

  const addMsg = useCallback((role: Role, text: string, extra?: Partial<Message>) => {
    setMessages(p => [...p, { id: uid(), role, text, ...extra }])
  }, [])

  const playVoice = async (id: string, text: string) => {
    if (playingId === id) { audioRef.current?.pause(); setPlayingId(null); return }
    setPlayingId(id)
    try {
      const r = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, language: lang }),
      })
      if (!r.ok) throw new Error('')
      const blob = await r.blob()
      if (audioRef.current) audioRef.current.pause()
      const a = new Audio(URL.createObjectURL(blob))
      audioRef.current = a
      a.play()
      a.onended = () => setPlayingId(null)
    } catch { setPlayingId(null) }
  }

  const stopBrowser = async () => {
    try { await fetch('/api/browser/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, session_id: userId }),
    }) } catch {}
    setBrowserFrame(null); setBrowserStep(''); setBrowserPct(0)
    setProgressStep(''); setProgressPct(0)
  }

  const callBackend = useCallback(async (text: string, phoneOverride?: string, messageType: string = 'text') => {
    if (!isOnline) { setErrorBanner('No internet connection'); return }
    setStatus('loading'); setLastFailedMsg(null)
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text, user_id: userId, phone: phoneOverride || phone || '',
          language: lang, message_type: messageType,
        }),
      })
      if (!r.ok) throw new Error(`${r.status}`)
      const d = await r.json()
      if (d.language && LANG_MAP[d.language]) setLang(d.language)
      if (d.voice_mode) setVoiceMode(true)
      let receiptUrl = d.receipt_url || null
      if (!receiptUrl && d.pdf_base64) {
        const blob = new Blob(
          [Uint8Array.from(atob(d.pdf_base64), c => c.charCodeAt(0))],
          { type: 'application/pdf' }
        )
        receiptUrl = URL.createObjectURL(blob)
      }
      addMsg('assistant', d.response || 'Something went wrong.', {
        screenshotUrl: d.screenshot_url || null,
        receiptUrl,
      })
      if (d.voice_mode && d.response) {
        setTimeout(() => playVoice(uid(), d.response), 500)
      }
    } catch {
      setLastFailedMsg(text)
      addMsg('system', '⚠️ Could not reach server. Click here to retry →')
    } finally {
      setStatus('idle')
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [phone, userId, lang, addMsg, isOnline])

  const retryLast = useCallback(() => {
    if (!lastFailedMsg) return
    const toResend = lastFailedMsg
    setLastFailedMsg(null)
    setMessages(prev => prev.filter(m => !m.text.includes('Could not reach server')))
    callBackend(toResend)
  }, [lastFailedMsg, callBackend])

  const send = useCallback((override?: string, type: 'text' | 'voice' | 'otp' = 'text') => {
    const msg = (override ?? input).trim()
    if (!msg || status === 'loading') return
    setInput(''); addMsg('user', msg)
    const isForm = /form|apply|card|ration|pan|voter|pension|kisan|ayush|mnrega|jan dhan|birth|caste|register/i.test(msg)
    if (isForm && !phone) { setPendingPrompt(msg); setPhoneModal(true); return }
    callBackend(msg, undefined, type)
  }, [input, status, phone, addMsg, callBackend])

  const handlePhone = (n: string) => {
    setPhone(n)
    setPhoneModal(false)
    addMsg('system', `Phone: ${n.replace('+91', '+91 ')}`)
    if (pendingPrompt) { callBackend(pendingPrompt, n); setPendingPrompt(null) }
  }

  const handleVault = (d: Record<string, string>) => {
    const txt = Object.entries(d).map(([k, v]) => `${k}: ${v}`).join('\n')
    addMsg('system', 'Loaded from vault')
    setInput(`Here is my information:\n${txt}`)
  }

  /* ── image upload ── */
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [voiceMode, setVoiceMode] = useState(false)

  const uploadDocument = useCallback(async (file: File) => {
    if (!file || !file.type.startsWith('image/')) return
    addMsg('user', `Sending document: ${file.name}`)
    setStatus('loading')
    try {
      const reader = new FileReader()
      const base64 = await new Promise<string>((resolve) => {
        reader.onload = () => resolve((reader.result as string).split(',')[1])
        reader.readAsDataURL(file)
      })
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: base64, user_id: userId, phone: phone || '', language: lang, message_type: 'image' }),
      })
      if (!r.ok) throw new Error('')
      const d = await r.json()
      addMsg('assistant', d.response || 'Document processed.', { screenshotUrl: d.screenshot_url || null, receiptUrl: d.receipt_url || null })
      if (d.voice_mode) setVoiceMode(true)
    } catch {
      addMsg('system', 'Upload failed. Try typing your info instead.')
    } finally { setStatus('idle') }
  }, [userId, phone, lang, addMsg])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadDocument(file)
    if (e.target) e.target.value = ''
  }

  /* ── selfie camera ── */
  const startCamera = useCallback(async () => {
    setCameraError(''); setCapturedSelfie(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }
      })
      streamRef.current = stream
      if (videoRef.current) { videoRef.current.srcObject = stream; videoRef.current.play() }
    } catch {
      setCameraError('Camera access denied. Please allow camera permission or upload a photo instead.')
    }
  }, [])

  const stopCamera = useCallback(() => {
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
    if (videoRef.current) { videoRef.current.srcObject = null }
  }, [])

  const captureSelfie = useCallback(() => {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth; canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(video, 0, 0)
    setCapturedSelfie(canvas.toDataURL('image/jpeg', 0.92))
    stopCamera()
  }, [stopCamera])

  const sendSelfie = useCallback(async () => {
    if (!capturedSelfie) return
    const base64 = capturedSelfie.split(',')[1]
    addMsg('user', 'Selfie captured')
    setStatus('loading'); setSelfieOpen(false); setCapturedSelfie(null)
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: base64, user_id: userId, phone: phone || '', language: lang, message_type: 'image' }),
      })
      if (!r.ok) throw new Error('')
      const d = await r.json()
      addMsg('assistant', d.response || 'Selfie processed.', { screenshotUrl: d.screenshot_url || null, receiptUrl: d.receipt_url || null })
      if (d.voice_mode) setVoiceMode(true)
    } catch {
      addMsg('system', 'Selfie upload failed. Try again or type your info instead.')
    } finally { setStatus('idle') }
  }, [capturedSelfie, userId, phone, lang, addMsg])

  useEffect(() => {
    if (selfieOpen) startCamera()
    else { stopCamera(); setCapturedSelfie(null); setCameraError('') }
  }, [selfieOpen, startCamera, stopCamera])

  /* ── voice recording ── */
  const stopVoice = useCallback(() => {
    if (mediaRecRef.current && mediaRecRef.current.state !== 'inactive') {
      mediaRecRef.current.stop()
    }
    if (recordingTimerRef.current) { clearInterval(recordingTimerRef.current); recordingTimerRef.current = null }
    setRecording(false); setRecordingTime(0)
  }, [])

  const startVoice = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      chunksRef.current = []
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        if (recordingTimerRef.current) { clearInterval(recordingTimerRef.current); recordingTimerRef.current = null }
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        if (blob.size < 100) {
          setErrorBanner('Recording too short — please speak clearly')
          setRecording(false); setLiveTxt(''); setRecordingTime(0)
          return
        }
        const fd = new FormData(); fd.append('audio', blob, 'recording.webm')
        try {
          setLiveTxt('Transcribing...')
          const res = await fetch('/api/voice', { method: 'POST', body: fd })
          if (res.ok) {
            const data = await res.json()
            if (data.text) { setInput(data.text); send(data.text, 'voice') }
            else { setErrorBanner('Could not understand audio — try typing instead') }
          } else { setErrorBanner('Voice service unavailable — try typing') }
        } catch { setErrorBanner('Voice upload failed — check connection') }
        setRecording(false); setLiveTxt(''); setRecordingTime(0)
      }
      mr.start()
      mediaRecRef.current = mr
      setRecording(true); setRecordingTime(0)
      const startTime = Date.now()
      recordingTimerRef.current = setInterval(() => {
        setRecordingTime(Math.round((Date.now() - startTime) / 1000))
        if (Date.now() - startTime > 30000) stopVoice()
      }, 1000)
    } catch { setErrorBanner('Microphone access denied — check browser permissions') }
  }, [send, stopVoice])

  const isFirst = messages.length <= 1

  return (
    <div className="flex flex-col h-screen" style={{ background: 'var(--canvas)' }}>
      {/* ── HEADER ── */}
      <header
        className="flex-shrink-0 flex items-center justify-between px-4 py-2.5"
        style={{ background: 'var(--surface-card)', borderBottom: '1px solid var(--hairline)' }}
      >
        <div className="flex items-center gap-3">
          <Link href="/" className="opacity-50 hover:opacity-100 transition-opacity">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5m7-7l-7 7 7 7" />
            </svg>
          </Link>
          <div>
            <div
              className="text-sm font-semibold"
              style={{ color: 'var(--ink)' }}
            >
              GramSetu
            </div>
            <div
              className="text-[11px]"
              style={{ color: 'var(--muted-soft)' }}
            >
              {status === 'loading' ? 'Working...' : 'AI &middot; Government Forms'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setVaultOpen(true)}
            className="text-[11px] px-2 py-1 rounded-md flex items-center gap-1 font-medium btn-outline"
            style={{ height: 30, fontSize: 11 }}
          >
            <Database size={10} /> Data
          </button>

          <div className="relative">
            <button
              onClick={() => setLangOpen(!langOpen)}
              className="text-[11px] px-2 py-1 rounded-md flex items-center gap-1 font-medium btn-outline"
              style={{ height: 30, fontSize: 11 }}
            >
              <Globe size={10} /> {LANG_MAP[lang] || 'Hindi'}
            </button>
            {langOpen && (
              <div
                className="absolute right-0 top-9 z-30 rounded-xl shadow-card py-1 w-32 overflow-hidden"
                style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)' }}
              >
                {Object.entries(LANG_MAP).map(([k, v]) => (
                  <button
                    key={k}
                    onClick={() => { setLang(k); setLangOpen(false) }}
                    className="w-full text-left text-xs px-3 py-1.5 transition-colors hover:bg-canvas"
                    style={{ color: k === lang ? 'var(--ink)' : 'var(--body)', fontWeight: k === lang ? 600 : 400 }}
                  >
                    {v}
                  </button>
                ))}
              </div>
            )}
          </div>

          {(browserFrame || status === 'loading') && (
            <button
              onClick={() => setBrowserMin(false)}
              className="text-[10px] px-2 py-1 rounded-md font-medium flex items-center gap-1"
              style={{
                height: 30,
                color: 'var(--success)',
                background: 'var(--surface-strong)',
                border: '1px solid var(--hairline)',
              }}
            >
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--success)' }} /> LIVE
            </button>
          )}

          <button
            onClick={() => {
              localStorage.removeItem(`gs_c_${userId}`)
              localStorage.removeItem('gs_s')
              setMessages([INITIAL_MSG]); setInput(''); setProgressStep(''); setProgressPct(0)
            }}
            className="text-[11px] px-2 py-1 rounded-md opacity-50 hover:opacity-100 transition-opacity"
            style={{ height: 30, border: '1px solid var(--hairline-strong)', background: 'transparent' }}
          >
            <RefreshCw size={12} color="var(--ink)" />
          </button>

          <button
            onClick={() => setPhoneModal(true)}
            className="text-[10px] px-2 py-1 rounded-md opacity-60 hover:opacity-100 transition-opacity"
            style={{ height: 30, border: '1px solid var(--hairline-strong)', background: 'transparent', color: 'var(--body)' }}
          >
            {mounted && phone ? `+91 ...${phone.slice(-4)}` : '+ Phone'}
          </button>
        </div>
      </header>

      {/* ── MESSAGES ── */}
      <div ref={listRef} className="flex-1 overflow-y-auto px-3 py-4 space-y-3">
        {messages.map(m => m.role === 'system' ? (
          <div key={m.id} className="flex justify-center">
            {m.text.includes('retry') ? (
              <button
                onClick={retryLast}
                className="text-[11px] px-2.5 py-1 rounded-full cursor-pointer transition-opacity hover:opacity-80"
                style={{ background: 'var(--surface-strong)', color: 'var(--error)' }}
              >
                {m.text.replace('→', '')} ↻
              </button>
            ) : (
              <span className="msg-system badge-pill">{m.text}</span>
            )}
          </div>
        ) : (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} fade-up`}>
            <div className={m.role === 'user' ? 'msg-user max-w-[82%] px-3.5 py-2.5' : 'msg-assistant max-w-[82%] px-3.5 py-2.5'}>
              <Bubble text={m.text} />
              {m.role === 'assistant' && (
                <button
                  onClick={() => playVoice(m.id, m.text)}
                  className="mt-2 flex items-center gap-1 text-[10px] font-medium tracking-wide px-2 py-0.5 rounded-full transition-colors"
                  style={{
                    background: playingId === m.id ? 'var(--primary)' : 'var(--surface-strong)',
                    color: playingId === m.id ? 'var(--on-primary)' : 'var(--muted)',
                  }}
                >
                  <Volume2 size={10} /> {playingId === m.id ? 'Playing' : 'Listen'}
                </button>
              )}
              {m.receiptUrl && (
                <div className="mt-2">
                  <a
                    href={m.receiptUrl}
                    target="_blank"
                    rel="noreferrer"
                    download={m.receiptUrl.startsWith('blob:') ? 'GramSetu_Receipt.pdf' : undefined}
                    className="btn-primary text-xs"
                    style={{ height: 34, fontSize: 12 }}
                  >
                    {m.receiptUrl.startsWith('blob:') || m.receiptUrl.includes('pdf') ? 'Download PDF' : 'Receipt'}
                  </a>
                </div>
              )}
              {m.screenshotUrl && (
                <div className="mt-2 cursor-pointer" onClick={() => setScreenshotModal(m.screenshotUrl!)}>
                  <img
                    src={m.screenshotUrl}
                    alt="Form"
                    className="max-w-xs rounded-lg"
                    style={{ border: '1px solid var(--hairline)' }}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                </div>
              )}
            </div>
          </div>
        ))}
        {status === 'loading' && (
          <div className="flex justify-start fade-up">
            <div className="msg-assistant px-4 py-3">
              <div className="flex gap-1.5">
                {[0, 1, 2].map(i => (
                  <span
                    key={i}
                    className="typing-dot w-1.5 h-1.5 rounded-full"
                    style={{ background: 'var(--muted-soft)' }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── PROGRESS ── */}
      <ProgressRow step={progressStep} pct={progressPct} />

      {/* ── SCHEME ROW ── */}
      {isFirst && schemes.length > 0 && (
        <div
          className="px-3 py-2"
          style={{ background: 'var(--surface-card)', borderTop: '1px solid var(--hairline)' }}
        >
          <div
            className="text-[10px] uppercase tracking-[0.96px] font-semibold mb-1.5"
            style={{ color: 'var(--muted)' }}
          >
            Popular
          </div>
          <div className="flex gap-1.5 overflow-x-auto">
            {schemes.slice(0, 5).map(s => (
              <button
                key={s.id}
                onClick={() => send(`Apply for ${s.name}`)}
                className="flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-all hover:border-ink"
                style={{ border: '1px solid var(--hairline)', background: 'var(--surface-card)', color: 'var(--ink)' }}
              >
                {s.emoji} {s.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── QUICK ROW ── */}
      {isFirst && (
        <div
          className="px-3 py-2 flex gap-1.5 overflow-x-auto"
          style={{ background: 'var(--surface-card)', borderTop: '1px solid var(--hairline)' }}
        >
          {QUICK.map(a => (
            <button
              key={a}
              onClick={() => send(`Apply for ${a}`)}
              className="flex-shrink-0 text-[11px] px-3 py-1.5 rounded-full font-medium transition-all hover:border-ink whitespace-nowrap"
              style={{ border: '1px solid var(--hairline)', background: 'var(--surface-card)', color: 'var(--ink)' }}
            >
              {a} &rarr;
            </button>
          ))}
        </div>
      )}

      {/* ── MCP WARNING ── */}
      {mcpWarn && (
        <div
          className="px-3 py-1 text-[11px]"
          style={{
            color: 'var(--body-strong)',
            background: 'var(--surface-strong)',
            borderTop: '1px solid var(--hairline)',
          }}
        >
          {mcpWarn}
        </div>
      )}

      {/* ── ERROR BANNER ── */}
      {errorBanner && (
        <div
          className="px-3 py-1.5 text-xs flex items-center justify-between"
          style={{
            color: 'var(--error)',
            background: 'var(--surface-strong)',
            borderTop: '1px solid var(--hairline)',
          }}
        >
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--error)' }} /> {errorBanner}
          </span>
          <button onClick={() => setErrorBanner('')} className="opacity-50 hover:opacity-100">&times;</button>
        </div>
      )}

      {/* ── OFFLINE BANNER ── */}
      {!isOnline && (
        <div
          className="px-3 py-1.5 text-xs flex items-center gap-1.5"
          style={{
            color: 'var(--body-strong)',
            background: 'var(--surface-strong)',
            borderTop: '1px solid var(--hairline)',
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--body-strong)' }} />
          You&apos;re offline — messages will be sent when reconnected
        </div>
      )}

      {/* ── LIVE TRANSCRIPT ── */}
      {liveTxt && (
        <div
          className="px-3 py-1.5 text-xs flex items-center gap-1.5"
          style={{ color: 'var(--body-strong)', background: 'var(--surface-strong)', borderTop: '1px solid var(--hairline)' }}
        >
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--body-strong)' }} /> {liveTxt}
        </div>
      )}

      {/* ── RECORDING INDICATOR ── */}
      {recording && (
        <div
          className="px-3 py-1.5 text-xs flex items-center gap-1.5"
          style={{ color: 'var(--error)', background: 'var(--surface-strong)', borderTop: '1px solid var(--hairline)' }}
        >
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--error)' }} />
          Recording {recordingTime}s &middot; tap send when done{recordingTime >= 28 ? ' (auto-send soon)' : ''}
        </div>
      )}

      {/* ── INPUT AREA ── */}
      <div
        className="flex-shrink-0 px-3 py-2.5 flex gap-2 items-end"
        style={{ background: 'var(--surface-card)', borderTop: '1px solid var(--hairline)' }}
      >
        <textarea
          ref={inputRef}
          rows={1}
          value={input}
          placeholder="Type or speak..."
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          className="flex-1 resize-none input-editorial"
          style={{ minHeight: 44, maxHeight: 120, height: 'auto', lineHeight: 1.5 }}
        />

        <button
          onClick={recording ? stopVoice : startVoice}
          className={`flex-shrink-0 h-10 rounded-full flex items-center justify-center transition-colors ${
            recording ? 'px-3 gap-1.5' : 'w-10'
          }`}
          style={{
            background: recording ? 'var(--error)' : 'var(--surface-strong)',
            color: recording ? 'var(--on-primary)' : 'var(--muted)',
          }}
          title={recording ? 'Send Voice' : 'Voice'}
        >
          {recording ? <><Send size={14} /><span className="text-xs font-medium">Send</span></> : <Mic size={14} />}
        </button>

        <input type="file" accept="image/*" ref={fileInputRef} onChange={handleFileChange} className="hidden" />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-colors"
          style={{ background: 'var(--surface-strong)', color: 'var(--muted)' }}
          title="Upload Aadhaar / Document photo"
        >
          <FileImage size={14} />
        </button>

        <button
          onClick={() => setSelfieOpen(true)}
          className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-colors"
          style={{ background: 'var(--surface-strong)', color: 'var(--muted)' }}
          title="Take a live selfie"
        >
          <User size={14} />
        </button>

        <button
          onClick={() => send()}
          disabled={!input.trim() || status === 'loading'}
          className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center disabled:opacity-30 transition-opacity"
          style={{ background: 'var(--primary)', color: 'var(--on-primary)' }}
          title="Send"
        >
          {status === 'loading' ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
        </button>

        <button
          onClick={() => setMcpOpen(!mcpOpen)}
          className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-colors"
          style={{
            background: mcpWarn ? 'var(--surface-strong)' : 'var(--surface-strong)',
            color: mcpWarn ? 'var(--body-strong)' : 'var(--muted-soft)',
          }}
          title="System Status"
        >
          {mcpWarn ? <WifiOff size={13} /> : <Wifi size={13} />}
        </button>
      </div>

      {/* ── MODALS ── */}
      {phoneModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.3)' }}
          onClick={() => { setPhoneModal(false); setPendingPrompt(null) }}
        >
          <div
            className="rounded-2xl p-5 mx-4 w-full max-w-sm"
            style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)' }}
            onClick={e => e.stopPropagation()}
          >
            <div className="text-sm font-semibold mb-1" style={{ color: 'var(--ink)' }}>Phone Number</div>
            <div className="text-xs mb-3" style={{ color: 'var(--muted)' }}>For OTP verification during form filling</div>
            <div className="flex gap-2">
              <span
                className="flex items-center px-2.5 rounded-lg text-sm"
                style={{ border: '1px solid var(--hairline-strong)', color: 'var(--body)' }}
              >
                +91
              </span>
              <input
                autoFocus
                type="tel"
                maxLength={10}
                placeholder="9876543210"
                value={phone.replace('+91', '')}
                onChange={e => setPhone('+91' + e.target.value.replace(/\D/g, ''))}
                onKeyDown={e => { if (e.key === 'Enter' && phone.length === 13) handlePhone(phone) }}
                className="flex-1 input-editorial"
                style={{ height: 44 }}
              />
            </div>
            <button
              onClick={() => handlePhone(phone)}
              disabled={phone.length !== 13}
              className="btn-primary w-full mt-3 text-sm justify-center disabled:opacity-30"
            >
              Continue
            </button>
          </div>
        </div>
      )}

      {screenshotModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.7)' }}
          onClick={() => setScreenshotModal(null)}
        >
          <button
            onClick={() => setScreenshotModal(null)}
            className="absolute top-4 right-4 text-white text-2xl"
          >
            &times;
          </button>
          <img
            src={screenshotModal}
            alt="Screenshot"
            className="max-w-full max-h-[90vh] rounded-lg"
            onClick={e => e.stopPropagation()}
          />
        </div>
      )}

      {selfieOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.6)' }}
          onClick={() => setSelfieOpen(false)}
        >
          <div
            className="rounded-2xl mx-4 w-full max-w-sm overflow-hidden"
            style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)' }}
            onClick={e => e.stopPropagation()}
          >
            <div
              className="flex items-center justify-between px-4 py-3"
              style={{ borderBottom: '1px solid var(--hairline)' }}
            >
              <span className="text-sm font-semibold" style={{ color: 'var(--ink)' }}>
                {capturedSelfie ? 'Review Selfie' : 'Take a Selfie'}
              </span>
              <button onClick={() => setSelfieOpen(false)} className="p-1 opacity-50 hover:opacity-100">
                <X size={16} color="var(--ink)" />
              </button>
            </div>
            <div className="relative bg-black aspect-[3/4] flex items-center justify-center">
              {!capturedSelfie ? (
                <>
                  <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
                  {cameraError && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/80 p-6">
                      <p className="text-white text-sm text-center">{cameraError}</p>
                    </div>
                  )}
                </>
              ) : (
                <img src={capturedSelfie} alt="Captured selfie" className="w-full h-full object-cover" />
              )}
            </div>
            <div className="px-4 py-3 flex gap-2">
              {!capturedSelfie ? (
                <button
                  onClick={captureSelfie}
                  disabled={!!cameraError}
                  className="btn-primary flex-1 justify-center disabled:opacity-30"
                  style={{ height: 42 }}
                >
                  <Camera size={16} /> Capture
                </button>
              ) : (
                <>
                  <button
                    onClick={() => { setCapturedSelfie(null); startCamera() }}
                    className="btn-outline flex-1 justify-center"
                    style={{ height: 42 }}
                  >
                    Retake
                  </button>
                  <button onClick={sendSelfie} className="btn-primary flex-1 justify-center gap-2" style={{ height: 42 }}>
                    <Send size={14} /> Send
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      <McpPanel servers={mcpSrv} open={mcpOpen} onClose={() => setMcpOpen(false)} />
      {vaultOpen && <VaultPanel userId={userId} onClose={() => setVaultOpen(false)} onUseData={handleVault} />}

      {/* ── BROWSER PREVIEW ── */}
      {browserFrame && (
        <div
          className={`fixed bottom-16 right-3 z-50 shadow-xl overflow-hidden transition-all ${
            browserMin
              ? 'w-11 h-11 rounded-full'
              : 'w-80 rounded-xl'
          }`}
          style={{
            background: browserMin ? 'var(--primary)' : 'var(--surface-card)',
            border: browserMin ? 'none' : '1px solid var(--hairline)',
          }}
        >
          {browserMin ? (
            <button onClick={() => setBrowserMin(false)} className="w-full h-full flex items-center justify-center" style={{ color: 'var(--on-primary)' }}>
              <span className="absolute inset-0 rounded-full animate-ping" style={{ background: 'rgba(22,163,74,0.2)' }} />
              <Monitor size={16} />
            </button>
          ) : (
            <>
              <div
                className="flex items-center justify-between px-3 py-2 text-white text-[10px] font-medium"
                style={{ background: 'var(--ink)' }}
              >
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--success)' }} /> Portal
                </div>
                <div className="flex gap-1">
                  <button onClick={() => setBrowserMin(true)} className="opacity-60 hover:opacity-100">&mdash;</button>
                  <button
                    onClick={() => { setBrowserFrame(null); setBrowserStep(''); setBrowserPct(0); setProgressStep(''); setProgressPct(0) }}
                    className="opacity-60 hover:opacity-100"
                  >
                    &times;
                  </button>
                </div>
              </div>
              <div className="aspect-[4/3] bg-zinc-900 relative">
                {browserFrame === 'loading' ? (
                  <div className="flex items-center justify-center h-full">
                    <Loader2 className="animate-spin" size={24} style={{ color: 'var(--success)' }} />
                  </div>
                ) : (
                  <img
                    src={browserFrame.startsWith('data:') ? browserFrame : `data:image/jpeg;base64,${browserFrame}`}
                    alt=""
                    className="w-full h-full object-contain"
                  />
                )}
                <div className="absolute bottom-2 left-2 right-2 px-2 py-1 rounded text-[10px] text-white/80 flex items-center justify-between" style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}>
                  <span className="truncate">{browserStep || 'Filling...'}</span>
                  <button
                    onClick={stopBrowser}
                    className="px-1.5 py-0.5 rounded text-white font-medium"
                    style={{ background: 'var(--error)' }}
                  >
                    STOP
                  </button>
                </div>
              </div>
              <div
                className="px-3 py-1.5 text-xs flex items-center justify-between"
                style={{ borderTop: '1px solid var(--hairline)' }}
              >
                <span className="truncate" style={{ color: 'var(--muted)' }}>{browserStep || 'Filling...'}</span>
                <span className="tabular-nums" style={{ color: 'var(--body)' }}>{Math.round(browserPct * 100)}%</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
