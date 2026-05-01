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
   PROGRESS ROW (minimal)
   ═══════════════════════════════════════════════════════════════ */

function ProgressRow({ step, pct }: { step: string; pct: number }) {
  if (!step || pct === 0) return null
  return (
    <div className="mx-4 mb-2 px-3 py-1.5 rounded-lg flex items-center gap-2 text-xs"
      style={{ background: '#f0fdf4', color: '#166534', border: '1px solid #bbf7d0' }}>
      <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
      <span>{step}</span>
      <span className="ml-auto tabular-nums opacity-60">{Math.round(pct * 100)}%</span>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   BUBBLE TEXT — clean markdown-like formatting
   ═══════════════════════════════════════════════════════════════ */

function Bubble({ text }: { text: string }) {
  return (
    <div className="space-y-0.5" suppressHydrationWarning>
      {text.split('\n').map((line, i) => (
        <p key={i} suppressHydrationWarning dangerouslySetInnerHTML={{
          __html: line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>') || '&nbsp;'
        }} />
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   VAULT PANEL — minimal slide-out
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
    <div className="fixed right-0 top-0 bottom-0 w-72 z-50 shadow-xl flex flex-col text-sm"
      style={{ background: '#fff', borderLeft: '1px solid #eee' }}>
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: '#eee' }}>
        <span className="font-semibold">Your Data</span>
        <button onClick={onClose} className="p-1 opacity-50 hover:opacity-100"><X size={16} /></button>
      </div>

      {!unlocked ? (
        <div className="flex-1 flex flex-col justify-center gap-3 px-5">
          <p className="text-xs text-gray-400 text-center">Enter your vault password</p>
          <input type="password" value={pass} onChange={e => setPass(e.target.value)} placeholder="Password"
            className="w-full px-3 py-2 rounded-lg text-sm border outline-none focus:border-black" />
          <button onClick={load}
            className="w-full py-2 bg-black text-white rounded-lg text-xs font-medium">Unlock</button>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {items.map(i => (
            <div key={i.id} className="p-2 rounded-lg bg-gray-50 group flex items-center justify-between">
              <div className="min-w-0">
                <div className="text-[10px] uppercase text-gray-400 font-medium">{i.label}</div>
                <div className="text-sm truncate">{i.value}</div>
              </div>
              <button onClick={() => remove(i.id)} className="opacity-0 group-hover:opacity-100 text-red-400 text-xs ml-2">×</button>
            </div>
          ))}
          <div className="pt-3 border-t space-y-2">
            <input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="Label"
              className="w-full px-2.5 py-1.5 text-xs rounded-lg border outline-none" />
            <input value={newVal} onChange={e => setNewVal(e.target.value)} placeholder="Value"
              className="w-full px-2.5 py-1.5 text-xs rounded-lg border outline-none" />
            <button onClick={save} className="w-full py-1.5 bg-black text-white rounded-lg text-xs">Add</button>
          </div>
        </div>
      )}

      {unlocked && items.length > 0 && (
        <button onClick={useAll} className="m-4 py-2 bg-black text-white rounded-lg text-xs font-medium">
          Use This Data
        </button>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   MCP PANEL — minimal
   ═══════════════════════════════════════════════════════════════ */

function McpPanel({ servers, open, onClose }: { servers: McpServer[]; open: boolean; onClose: () => void }) {
  if (!open) return null
  return (
    <div className="fixed right-0 top-0 bottom-0 w-60 z-40 shadow-lg flex flex-col text-sm"
      style={{ background: '#fff', borderLeft: '1px solid #eee' }}>
      <div className="flex items-center justify-between px-3 py-3 border-b" style={{ borderColor: '#eee' }}>
        <span className="font-semibold text-xs flex items-center gap-1.5"><Activity size={12} /> Systems</span>
        <button onClick={onClose} className="opacity-50 hover:opacity-100"><X size={14} /></button>
      </div>
      <div className="p-3 space-y-2">
        {servers.map(s => (
          <div key={s.name} className="p-2 rounded-lg border text-xs" style={{ borderColor: '#eee' }}>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.online ? '#22c55e' : '#ef4444' }} />
              <span className="font-medium">{s.name}</span>
            </div>
            <div className="text-gray-400 mt-0.5">:{s.port} · {s.online ? s.lastPing : 'offline'}</div>
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
  const saved = typeof window !== 'undefined' ? (() => { try { return JSON.parse(localStorage.getItem('gs_s') || 'null') } catch { return null } })() : null
  const [messages, setMessages] = useState<Message[]>(() => {
    if (saved) { const m = loadMessages(saved.uid); if (m?.length) return m }
    return [INITIAL_MSG]
  })
  const [input, setInput] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [userId] = useState(() => saved?.uid ?? 'u_' + uid())
  const [phone, setPhone] = useState(saved?.phone ?? '')
  const [lang, setLang] = useState(saved?.lang ?? 'hi')
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

  function loadMessages(id: string): Message[] | null {
    try { return JSON.parse(localStorage.getItem(`gs_c_${id}`) || 'null') } catch { return null }
  }

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

  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' }) }, [messages, status])

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
        const off = []; if (!d.digilocker) off.push('DigiLocker'); if (!d.browser) off.push('Browser')
        setMcpWarn(off.length ? `⚠ ${off.join(', ')} unavailable` : '')
      } catch {}
    }
    f(); return () => { c = true }
  }, [mcpOpen])

  /* ── WebSocket (browser preview — works on HTTP only) ── */
  useEffect(() => {
    const isHttps = window.location.protocol === 'https:'
    if (isHttps) return  // No WebSocket on HTTPS (VPS doesn't have SSL)

    const p = 'ws'
    let ws: WebSocket | null = null; let rt: ReturnType<typeof setTimeout> | null = null; let a = true
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
        const r = await fetch('/api/schemes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: 'show', language: 'hi' }) })
        if (r.ok) { const d = await r.json(); if (d.schemes) setSchemes(d.schemes) }
      } catch {}
    })()
  }, [])

  /* ── voice check ──────────────────── */
  useEffect(() => {
    if (typeof window !== 'undefined' && !navigator.mediaDevices?.getUserMedia) setRecording(false)
  }, [])

  const addMsg = useCallback((role: Role, text: string, extra?: Partial<Message>) => {
    setMessages(p => [...p, { id: uid(), role, text, ...extra }])
  }, [])

  const playVoice = async (id: string, text: string) => {
    if (playingId === id) { audioRef.current?.pause(); setPlayingId(null); return }
    setPlayingId(id)
    try {
      const r = await fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, language: lang }) })
      if (!r.ok) throw new Error('')
      const blob = await r.blob()
      if (audioRef.current) audioRef.current.pause()
      const a = new Audio(URL.createObjectURL(blob)); audioRef.current = a; a.play(); a.onended = () => setPlayingId(null)
    } catch { setPlayingId(null) }
  }

  const stopBrowser = async () => {
    try { await fetch('/api/browser/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone, session_id: userId }) }) } catch {}
    setBrowserFrame(null); setBrowserStep(''); setBrowserPct(0); setProgressStep(''); setProgressPct(0)
  }

  const callBackend = useCallback(async (text: string, phoneOverride?: string) => {
    if (!isOnline) { setErrorBanner('No internet connection'); return }
    setStatus('loading'); setLastFailedMsg(null)
    try {
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text, user_id: userId, phone: phoneOverride || phone || '', language: lang }) })
      if (!r.ok) throw new Error(`${r.status}`)
      const d = await r.json()
      if (d.language && LANG_MAP[d.language]) setLang(d.language)
      if (d.voice_mode) setVoiceMode(true)
      // Build receipt URL from either API endpoint or PDF base64
      let receiptUrl = d.receipt_url || null
      if (!receiptUrl && d.pdf_base64) {
        const blob = new Blob([Uint8Array.from(atob(d.pdf_base64), c => c.charCodeAt(0))], { type: 'application/pdf' })
        receiptUrl = URL.createObjectURL(blob)
      }
      addMsg('assistant', d.response || 'Something went wrong.', { screenshotUrl: d.screenshot_url || null, receiptUrl })
      // Auto-play voice in voice-first mode
      if (d.voice_mode && d.response) {
        setTimeout(() => playVoice(uid(), d.response), 500)
      }
    } catch {
      setLastFailedMsg(text)
      addMsg('system', '⚠️ Could not reach server. Click here to retry →')
    }
    finally { setStatus('idle'); setTimeout(() => inputRef.current?.focus(), 100) }
  }, [phone, userId, lang, addMsg, isOnline])

  const retryLast = useCallback(() => {
    if (!lastFailedMsg) return
    const toResend = lastFailedMsg
    setLastFailedMsg(null)
    setMessages(prev => prev.filter(m => !m.text.includes('Could not reach server')))
    callBackend(toResend)
  }, [lastFailedMsg, callBackend])

  const send = useCallback((override?: string) => {
    const msg = (override ?? input).trim()
    if (!msg || status === 'loading') return
    setInput(''); addMsg('user', msg)
    const isForm = /form|apply|card|ration|pan|voter|pension|kisan|ayush|mnrega|jan dhan|birth|caste|register/i.test(msg)
    if (isForm && !phone) { setPendingPrompt(msg); setPhoneModal(true); return }
    callBackend(msg)
  }, [input, status, phone, addMsg, callBackend])

  const handlePhone = (n: string) => { setPhone(n); setPhoneModal(false); addMsg('system', `Phone: ${n.replace('+91', '+91 ')}`); if (pendingPrompt) { callBackend(pendingPrompt, n); setPendingPrompt(null) } }

  const handleVault = (d: Record<string, string>) => {
    const txt = Object.entries(d).map(([k, v]) => `${k}: ${v}`).join('\n')
    addMsg('system', 'Loaded from vault')
    setInput(`Here is my information:\n${txt}`)
  }

  /* ── image upload (document scan) ── */
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [voiceMode, setVoiceMode] = useState(false)

  const uploadDocument = useCallback(async (file: File) => {
    if (!file || !file.type.startsWith('image/')) return
    addMsg('user', `📸 Sending document: ${file.name}`)
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
      addMsg('system', '⚠️ Upload failed. Try typing your info instead.')
    }
    finally { setStatus('idle') }
  }, [userId, phone, lang, addMsg])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadDocument(file)
    if (e.target) e.target.value = ''
  }

  /* ── live selfie camera ── */
  const startCamera = useCallback(async () => {
    setCameraError(''); setCapturedSelfie(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        videoRef.current.play()
      }
    } catch {
      setCameraError('Camera access denied. Please allow camera permission or upload a photo instead.')
    }
  }, [])

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
  }, [])

  const captureSelfie = useCallback(() => {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(video, 0, 0)
    const dataUrl = canvas.toDataURL('image/jpeg', 0.92)
    setCapturedSelfie(dataUrl)
    stopCamera()
  }, [stopCamera])

  const sendSelfie = useCallback(async () => {
    if (!capturedSelfie) return
    const base64 = capturedSelfie.split(',')[1]
    addMsg('user', '📸 Selfie captured')
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
      addMsg('system', '⚠️ Selfie upload failed. Try again or type your info instead.')
    } finally { setStatus('idle') }
  }, [capturedSelfie, userId, phone, lang, addMsg])

  useEffect(() => {
    if (selfieOpen) startCamera()
    else { stopCamera(); setCapturedSelfie(null); setCameraError('') }
  }, [selfieOpen, startCamera, stopCamera])

  /* ── simple voice (MediaRecorder upload) ── */
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
        if (blob.size < 100) { setErrorBanner('Recording too short — please speak clearly'); setRecording(false); setLiveTxt(''); setRecordingTime(0); return }
        const fd = new FormData()
        fd.append('audio', blob, 'recording.webm')
        try {
          setLiveTxt('Transcribing...')
          const res = await fetch('/api/voice', { method: 'POST', body: fd })
          if (res.ok) {
            const data = await res.json()
            if (data.text) {
              setInput(data.text)
              send(data.text)
            } else {
              setErrorBanner('Could not understand audio — try typing instead')
            }
          } else {
            setErrorBanner('Voice service unavailable — try typing')
          }
        } catch { setErrorBanner('Voice upload failed — check connection') }
        setRecording(false); setLiveTxt(''); setRecordingTime(0)
      }
      mr.start()
      mediaRecRef.current = mr
      setRecording(true); setRecordingTime(0)
      const startTime = Date.now()
      recordingTimerRef.current = setInterval(() => {
        setRecordingTime(Math.round((Date.now() - startTime) / 1000))
        if (Date.now() - startTime > 30000) stopVoice() // 30s max
      }, 1000)
    } catch { setErrorBanner('Microphone access denied — check browser permissions') }
  }, [send, stopVoice])

  /* ── render ──────────────────────── */
  const isFirst = messages.length <= 1

  return (
    <div className="flex flex-col h-screen" style={{ background: '#fafafa' }}>
      {/* HEADER */}
      <header className="flex-shrink-0 flex items-center justify-between px-4 py-2.5 bg-white border-b" style={{ borderColor: '#eee' }}>
        <div className="flex items-center gap-3">
          <Link href="/" className="opacity-50 hover:opacity-100"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5m7-7l-7 7 7 7"/></svg></Link>
          <div>
            <div className="text-sm font-semibold">GramSetu</div>
            <div className="text-[11px] text-gray-400">{status === 'loading' ? 'Working…' : 'AI · Government Forms'}</div>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={() => setVaultOpen(true)} className="text-[11px] px-2 py-1 rounded-md flex items-center gap-1 font-medium border" style={{ borderColor: '#d4d4d4' }}>
            <Database size={10} /> Data
          </button>
          <div className="relative">
            <button onClick={() => setLangOpen(!langOpen)} className="text-[11px] px-2 py-1 rounded-md flex items-center gap-1 border" style={{ borderColor: '#d4d4d4' }}>
              <Globe size={10} /> {LANG_MAP[lang] || 'Hindi'}
            </button>
            {langOpen && (
              <div className="absolute right-0 top-8 z-30 rounded-lg shadow-lg py-1 w-32 bg-white border" style={{ borderColor: '#eee' }}>
                {Object.entries(LANG_MAP).map(([k, v]) => (
                  <button key={k} onClick={() => { setLang(k); setLangOpen(false) }}
                    className={`w-full text-left text-xs px-3 py-1.5 hover:bg-gray-50 ${k === lang ? 'font-semibold' : ''}`}>{v}</button>
                ))}
              </div>
            )}
          </div>
          {(browserFrame || status === 'loading') && (
            <button onClick={() => setBrowserMin(false)} className="text-[10px] px-2 py-1 rounded-md font-medium border flex items-center gap-1" style={{ borderColor: '#22c55e', color: '#15803d', background: '#f0fdf4' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" /> LIVE
            </button>
          )}
          <button onClick={() => { localStorage.removeItem(`gs_c_${userId}`); localStorage.removeItem('gs_s'); setMessages([INITIAL_MSG]); setInput(''); setProgressStep(''); setProgressPct(0) }}
            className="text-[11px] px-2 py-1 rounded-md border opacity-50 hover:opacity-100" style={{ borderColor: '#d4d4d4' }}>
            <RefreshCw size={12} />
          </button>
          <button onClick={() => setPhoneModal(true)} className="text-[10px] px-2 py-1 rounded-md border opacity-60 hover:opacity-100" style={{ borderColor: '#d4d4d4' }}>
            {phone ? `+91 ···${phone.slice(-4)}` : '+ Phone'}
          </button>
        </div>
      </header>

      {/* MESSAGES */}
      <div ref={listRef} className="flex-1 overflow-y-auto px-3 py-4 space-y-3">
        {messages.map(m => m.role === 'system' ? (
          <div key={m.id} className="flex justify-center">
            {m.text.includes('retry') ? (
              <button onClick={retryLast} className="text-[11px] px-2.5 py-1 rounded-full cursor-pointer hover:opacity-80" style={{ background: '#fee2e2', color: '#dc2626' }}>
                {m.text.replace('→', '')} ↻
              </button>
            ) : (
              <div className="text-[11px] px-2.5 py-1 rounded-full" style={{ background: '#f5f0e8', color: '#8c7851' }}>{m.text}</div>
            )}
          </div>
        ) : (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[84%] px-3.5 py-2.5 text-sm leading-relaxed rounded-2xl ${
              m.role === 'user' ? 'text-white' : ''
            }`} style={m.role === 'user' ? { background: '#111' } : { background: '#fff', border: '1px solid #eee' }}>
              <Bubble text={m.text} />
              {m.role === 'assistant' && (
                <button onClick={() => playVoice(m.id, m.text)}
                  className={`mt-2 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide px-2 py-0.5 rounded ${
                    playingId === m.id ? 'bg-black text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}>
                  <Volume2 size={10} /> {playingId === m.id ? 'Playing' : 'Listen'}
                </button>
              )}
              {m.receiptUrl && (
                <div className="mt-2">
                  <a href={m.receiptUrl} target="_blank" rel="noreferrer" download={m.receiptUrl.startsWith('blob:') ? 'GramSetu_Receipt.pdf' : undefined}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-green-600 hover:bg-green-700">
                    {m.receiptUrl.startsWith('blob:') || m.receiptUrl.includes('pdf') ? '📄 Download PDF' : '📄 Receipt'}
                  </a>
                </div>
              )}
              {m.screenshotUrl && (
                <div className="mt-2 cursor-pointer" onClick={() => setScreenshotModal(m.screenshotUrl!)}>
                  <img src={m.screenshotUrl} alt="Form" className="max-w-xs rounded-lg border" style={{ borderColor: '#eee' }}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                </div>
              )}
            </div>
          </div>
        ))}
        {status === 'loading' && (
          <div className="flex justify-start">
            <div className="px-4 py-3 rounded-2xl" style={{ background: '#fff', border: '1px solid #eee' }}>
              <div className="flex gap-1.5">
                {[0,1,2].map(i => <span key={i} className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: '#999', animationDelay: `${i*0.15}s` }} />)}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* PROGRESS ROW */}
      <ProgressRow step={progressStep} pct={progressPct} />

      {/* SCHEME ROW */}
      {isFirst && schemes.length > 0 && (
        <div className="px-3 py-2 border-t bg-white" style={{ borderColor: '#eee' }}>
          <div className="text-[10px] text-gray-400 uppercase tracking-wider mb-1.5">Popular</div>
          <div className="flex gap-1.5 overflow-x-auto">
            {schemes.slice(0, 5).map(s => (
              <button key={s.id} onClick={() => send(`Apply for ${s.name}`)}
                className="flex-shrink-0 px-3 py-1.5 rounded-full text-xs border hover:border-black transition-colors"
                style={{ borderColor: '#e5e5e5' }}>{s.emoji} {s.name}</button>
            ))}
          </div>
        </div>
      )}

      {/* QUICK ROW */}
      {isFirst && (
        <div className="px-3 py-2 border-t bg-white flex gap-1.5 overflow-x-auto" style={{ borderColor: '#eee' }}>
          {QUICK.map(a => (
            <button key={a} onClick={() => send(`Apply for ${a}`)}
              className="flex-shrink-0 text-[11px] px-3 py-1.5 rounded-full border hover:border-black transition-colors whitespace-nowrap"
              style={{ borderColor: '#e5e5e5' }}>{a} →</button>
          ))}
        </div>
      )}

      {/* MCP WARNING */}
      {mcpWarn && <div className="px-3 py-1 text-[11px] text-amber-700 bg-amber-50 border-t border-amber-100">{mcpWarn}</div>}

      {/* ERROR BANNER */}
      {errorBanner && (
        <div className="px-3 py-1.5 text-xs text-red-700 bg-red-50 border-t border-red-100 flex items-center justify-between">
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-red-500" /> {errorBanner}</span>
          <button onClick={() => setErrorBanner('')} className="opacity-50 hover:opacity-100">×</button>
        </div>
      )}

      {/* OFFLINE BANNER */}
      {!isOnline && (
        <div className="px-3 py-1.5 text-xs text-orange-700 bg-orange-50 border-t border-orange-100 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-orange-500" /> You're offline — messages will be sent when reconnected
        </div>
      )}

      {/* LIVE TRANSCRIPT */}
      {liveTxt && (
        <div className="px-3 py-1.5 text-xs text-blue-700 bg-blue-50 border-t border-blue-100 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" /> {liveTxt}
        </div>
      )}

      {/* RECORDING INDICATOR */}
      {recording && (
        <div className="px-3 py-1.5 text-xs text-red-700 bg-red-50 border-t border-red-100 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" /> Recording {recordingTime}s · tap send when done {recordingTime >= 28 ? '(auto-send soon)' : ''}
        </div>
      )}

      {/* INPUT */}
      <div className="flex-shrink-0 px-3 py-2.5 flex gap-2 items-end border-t bg-white" style={{ borderColor: '#eee' }}>
        <textarea ref={inputRef} rows={1} value={input}
          placeholder="Type or speak…"
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          className="flex-1 resize-none px-3.5 py-2.5 rounded-xl text-sm outline-none"
          style={{ border: '1px solid #e5e5e5', minHeight: 40, maxHeight: 120, lineHeight: 1.5 }} />

        <button onClick={recording ? stopVoice : startVoice}
          className={`flex-shrink-0 h-9 rounded-full flex items-center justify-center transition-colors ${recording ? 'px-3 gap-1.5' : 'w-9'}`}
          style={{ background: recording ? '#dc2626' : '#f5f5f5', color: recording ? '#fff' : '#666' }} title={recording ? 'Send Voice' : 'Voice'}>
          {recording ? <><Send size={14} /><span className="text-xs font-medium">Send</span></> : <Mic size={14} />}
        </button>

        <input type="file" accept="image/*" ref={fileInputRef}
          onChange={handleFileChange} className="hidden" />
        <button onClick={() => fileInputRef.current?.click()}
          className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-colors"
          style={{ background: '#f5f5f5', color: '#666' }} title="Upload Aadhaar / Document photo">
          <FileImage size={14} />
        </button>
        <button onClick={() => setSelfieOpen(true)}
          className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-colors"
          style={{ background: '#f5f5f5', color: '#666' }} title="Take a live selfie">
          <User size={14} />
        </button>

        <button onClick={() => send()} disabled={!input.trim() || status === 'loading'}
          className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center disabled:opacity-30 transition-colors"
          style={{ background: '#111', color: '#fff' }} title="Send">
          {status === 'loading' ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
        </button>

        <button onClick={() => setMcpOpen(!mcpOpen)}
          className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-colors"
          style={{ background: mcpWarn ? '#fef3c7' : '#f5f5f5', color: mcpWarn ? '#b45309' : '#999' }} title="System Status">
          {mcpWarn ? <WifiOff size={13} /> : <Wifi size={13} />}
        </button>
      </div>

      {/* MODALS */}
      {phoneModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,.3)' }}
          onClick={() => { setPhoneModal(false); setPendingPrompt(null) }}>
          <div className="bg-white rounded-2xl p-5 mx-4 w-full max-w-sm border" style={{ borderColor: '#eee' }} onClick={e => e.stopPropagation()}>
            <div className="text-sm font-semibold mb-1">Phone Number</div>
            <div className="text-xs text-gray-400 mb-3">For OTP verification during form filling</div>
            <div className="flex gap-2">
              <span className="flex items-center px-2.5 rounded-lg text-sm border" style={{ borderColor: '#e5e5e5' }}>+91</span>
              <input autoFocus type="tel" maxLength={10} placeholder="9876543210"
                value={phone.replace('+91', '')} onChange={e => setPhone('+91' + e.target.value.replace(/\D/g, ''))}
                onKeyDown={e => { if (e.key === 'Enter' && phone.length === 13) handlePhone(phone) }}
                className="flex-1 px-3 py-2 rounded-lg text-sm outline-none border" style={{ borderColor: '#e5e5e5' }} />
            </div>
            <button onClick={() => handlePhone(phone)} disabled={phone.length !== 13}
              className="w-full mt-3 py-2 rounded-lg text-sm font-medium text-white bg-black disabled:opacity-30">Continue</button>
          </div>
        </div>
      )}

      {screenshotModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,.7)' }} onClick={() => setScreenshotModal(null)}>
          <button onClick={() => setScreenshotModal(null)} className="absolute top-4 right-4 text-white text-2xl">×</button>
          <img src={screenshotModal} alt="Screenshot" className="max-w-full max-h-[90vh] rounded-lg" onClick={e => e.stopPropagation()} />
        </div>
      )}

      {selfieOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,.6)' }} onClick={() => setSelfieOpen(false)}>
          <div className="bg-white rounded-2xl mx-4 w-full max-w-sm overflow-hidden" style={{ border: '1px solid #eee' }} onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: '#eee' }}>
              <span className="text-sm font-semibold">{capturedSelfie ? 'Review Selfie' : 'Take a Selfie'}</span>
              <button onClick={() => setSelfieOpen(false)} className="p-1 opacity-50 hover:opacity-100"><X size={16} /></button>
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
                <button onClick={captureSelfie} disabled={!!cameraError}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-white bg-black disabled:opacity-30 flex items-center justify-center gap-2">
                  <Camera size={16} /> Capture
                </button>
              ) : (
                <>
                  <button onClick={() => { setCapturedSelfie(null); startCamera() }}
                    className="flex-1 py-2.5 rounded-xl text-sm font-medium border" style={{ borderColor: '#e5e5e5' }}>
                    Retake
                  </button>
                  <button onClick={sendSelfie}
                    className="flex-1 py-2.5 rounded-xl text-sm font-medium text-white bg-black flex items-center justify-center gap-2">
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

      {/* BROWSER PREVIEW */}
      {browserFrame && (
        <div className={`fixed bottom-16 right-3 z-50 shadow-lg overflow-hidden transition-all ${
          browserMin ? 'w-11 h-11 rounded-full bg-black' : 'w-80 rounded-xl bg-white border'}`} style={{ borderColor: '#eee' }}>
          {browserMin ? (
            <button onClick={() => setBrowserMin(false)} className="w-full h-full flex items-center justify-center text-white">
              <span className="absolute inset-0 rounded-full bg-green-500/20 animate-ping" />
              <Monitor size={16} />
            </button>
          ) : (
            <>
              <div className="flex items-center justify-between px-3 py-2 bg-black text-white text-[10px] font-medium">
                <div className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" /> Portal</div>
                <div className="flex gap-1">
                  <button onClick={() => setBrowserMin(true)} className="opacity-60 hover:opacity-100">—</button>
                  <button onClick={() => { setBrowserFrame(null); setBrowserStep(''); setBrowserPct(0); setProgressStep(''); setProgressPct(0) }} className="opacity-60 hover:opacity-100">×</button>
                </div>
              </div>
              <div className="aspect-[4/3] bg-zinc-900 relative">
                {browserFrame === 'loading' ? (
                  <div className="flex items-center justify-center h-full"><Loader2 className="text-green-500 animate-spin" size={24} /></div>
                ) : (
                  <img src={browserFrame.startsWith('data:') ? browserFrame : `data:image/jpeg;base64,${browserFrame}`} alt="" className="w-full h-full object-contain" />
                )}
                <div className="absolute bottom-2 left-2 right-2 bg-black/60 backdrop-blur px-2 py-1 rounded text-[10px] text-white/80 flex items-center justify-between">
                  <span className="truncate">{browserStep || 'Filling…'}</span>
                  <button onClick={stopBrowser} className="bg-red-500 px-1.5 py-0.5 rounded text-white font-medium">STOP</button>
                </div>
              </div>
              <div className="px-3 py-1.5 border-t text-xs flex items-center justify-between" style={{ borderColor: '#eee' }}>
                <span className="text-gray-500 truncate">{browserStep || 'Filling…'}</span>
                <span className="tabular-nums">{Math.round(browserPct * 100)}%</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
