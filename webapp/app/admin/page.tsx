'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowLeft, RefreshCw, Shield, Clock, CheckCircle2, AlertTriangle,
  Loader2, Search, Filter, LogOut,
} from 'lucide-react'

interface AuditEntry {
  id: string
  timestamp: string
  user_id: string
  phone: string
  action: string
  form_type: string
  status: string
  details: string
  latency_ms?: number
}

const ADMIN_TOKEN = 'gramsetu-admin-2025'
const POLL_INTERVAL = 5000

function getStatusStyle(status: string) {
  const normalized = status.toLowerCase().replace(/[\s-]/g, '_')
  const map: Record<string, { bg: string; text: string }> = {
    completed:   { bg: '#dcfce7', text: '#166534' },
    success:     { bg: '#dcfce7', text: '#166534' },
    in_progress: { bg: '#fef3c7', text: '#92400e' },
    pending:     { bg: '#fef3c7', text: '#92400e' },
    processing:  { bg: '#dbeafe', text: '#1e40af' },
    failed:      { bg: '#fee2e2', text: '#991b1b' },
    error:       { bg: '#fee2e2', text: '#991b1b' },
  }
  return map[normalized] || { bg: 'var(--surface-strong)', text: 'var(--body)' }
}

function formatTimestamp(ts: string) {
  try {
    const d = new Date(ts)
    return d.toLocaleString('en-IN', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch { return ts }
}

function PasswordGate({ onUnlock }: { onUnlock: () => void }) {
  const [pw, setPw] = useState('')
  const [error, setError] = useState(false)

  const envPw = typeof window !== 'undefined'
    ? (window as unknown as Record<string, string>)?.NEXT_PUBLIC_ADMIN_PASSWORD
    : undefined

  const correctPw = envPw || 'gramsetu2025'

  const submit = () => {
    if (pw === correctPw) {
      if (typeof window !== 'undefined') sessionStorage.setItem('gramsetu_admin_auth', '1')
      onUnlock()
    } else {
      setError(true)
      setTimeout(() => setError(false), 2000)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--canvas)' }}>
      <div
        className="w-full max-w-sm rounded-2xl p-6"
        style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)' }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Shield size={20} color="var(--ink)" />
          <h2 className="font-semibold text-base" style={{ color: 'var(--ink)' }}>Admin Dashboard</h2>
        </div>
        <p className="text-sm mb-4" style={{ color: 'var(--body)' }}>
          Enter the admin password to access the audit dashboard.
        </p>
        <form onSubmit={(e) => { e.preventDefault(); submit() }}>
          <input
            autoFocus
            type="password"
            placeholder="Password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            className="input-editorial w-full mb-3"
            style={{ height: 44 }}
          />
          {error && <p className="text-xs mb-2" style={{ color: 'var(--error)' }}>Incorrect password</p>}
          <button type="submit" className="btn-primary w-full text-sm justify-center">
            Unlock
          </button>
        </form>
        <Link href="/" className="block text-center text-xs mt-3" style={{ color: 'var(--muted)' }}>
          &larr; Back to home
        </Link>
      </div>
    </div>
  )
}

function StatsRow({ entries }: { entries: AuditEntry[] }) {
  const total = entries.length
  const completed = entries.filter(e => ['completed', 'success'].includes(e.status?.toLowerCase())).length
  const inProgress = entries.filter(e => ['in_progress', 'pending', 'processing'].includes(e.status?.toLowerCase().replace(/[\s-]/g, '_'))).length
  const latencies = entries.filter(e => e.latency_ms).map(e => e.latency_ms!)
  const avgLatency = latencies.length ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length) : 0

  const cards = [
    { label: 'Total Applications', value: total, icon: <Filter size={14} /> },
    { label: 'Completed', value: completed, icon: <CheckCircle2 size={14} style={{ color: 'var(--success)' }} /> },
    { label: 'In Progress', value: inProgress, icon: <Clock size={14} style={{ color: '#92400e' }} /> },
    { label: 'Avg Latency', value: avgLatency ? `${avgLatency}ms` : '—', icon: <AlertTriangle size={14} style={{ color: '#1e40af' }} /> },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      {cards.map(c => (
        <div key={c.label} className="feature-card p-4">
          <div className="flex items-center gap-2 mb-1">
            {c.icon}
            <span className="text-xs" style={{ color: 'var(--muted)' }}>{c.label}</span>
          </div>
          <p className="text-xl font-semibold" style={{ color: 'var(--ink)' }}>{c.value}</p>
        </div>
      ))}
    </div>
  )
}

export default function AdminPage() {
  const [authed, setAuthed] = useState(false)
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [filterType, setFilterType] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined' && sessionStorage.getItem('gramsetu_admin_auth') === '1') {
      setAuthed(true)
    }
  }, [])

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(`/api/audit-logs?token=${ADMIN_TOKEN}`)
      if (!res.ok) return
      const data = await res.json()
      if (Array.isArray(data.logs)) setEntries(data.logs)
      else if (Array.isArray(data)) setEntries(data)
    } catch {} finally { setLoading(false) }
  }, [])

  useEffect(() => {
    if (!authed) return
    fetchLogs()
    if (paused) return
    const interval = setInterval(fetchLogs, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [authed, fetchLogs, paused])

  const formTypes = Array.from(new Set(entries.map(e => e.form_type).filter(Boolean)))
  const filtered = entries.filter(e => {
    if (filterType !== 'all' && e.form_type !== filterType) return false
    if (searchTerm) {
      const q = searchTerm.toLowerCase()
      return (e.user_id || '').toLowerCase().includes(q) ||
        (e.phone || '').toLowerCase().includes(q) ||
        (e.action || '').toLowerCase().includes(q) ||
        (e.details || '').toLowerCase().includes(q)
    }
    return true
  })

  if (!authed) return <PasswordGate onUnlock={() => setAuthed(true)} />

  return (
    <div className="min-h-screen" style={{ background: 'var(--canvas)' }}>
      <header
        className="sticky top-0 z-10 flex items-center justify-between px-6 py-3"
        style={{ background: 'var(--surface-card)', borderBottom: '1px solid var(--hairline)' }}
      >
        <div className="flex items-center gap-3">
          <Link href="/" style={{ color: 'var(--muted)' }}><ArrowLeft size={18} /></Link>
          <div>
            <p className="font-semibold text-sm leading-tight flex items-center gap-1.5" style={{ color: 'var(--ink)' }}>
              <Shield size={14} /> Admin Dashboard
            </p>
            <p className="text-xs" style={{ color: 'var(--muted)' }}>Live audit feed &middot; {entries.length} records</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setPaused(!paused)} className="btn-outline text-xs" style={{ height: 30, fontSize: 11 }}>
            {paused ? 'Resume' : 'Pause'}
          </button>
          <button onClick={fetchLogs} className="btn-outline text-xs" style={{ height: 30, fontSize: 11 }}>
            <RefreshCw size={11} /> Refresh
          </button>
          <button onClick={() => { sessionStorage.removeItem('gramsetu_admin_auth'); setAuthed(false) }} className="btn-outline text-xs" style={{ height: 30, fontSize: 11 }}>
            <LogOut size={11} /> Logout
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-6">
        <StatsRow entries={entries} />

        <div className="flex flex-wrap gap-3 mb-4">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search size={14} className="absolute left-3 top-2.5" style={{ color: 'var(--muted)' }} />
            <input
              type="text"
              placeholder="Search by user, phone, action..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg text-xs outline-none"
              style={{ border: '1px solid var(--hairline-strong)', background: 'var(--surface-card)' }}
            />
          </div>
          <select
            value={filterType}
            onChange={e => setFilterType(e.target.value)}
            className="text-xs px-3 py-2 rounded-lg outline-none"
            style={{ border: '1px solid var(--hairline-strong)', background: 'var(--surface-card)', color: 'var(--ink)' }}
          >
            <option value="all">All form types</option>
            {formTypes.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={24} className="animate-spin" style={{ color: 'var(--muted)' }} />
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-sm" style={{ color: 'var(--muted)' }}>
              No audit entries {searchTerm || filterType !== 'all' ? 'match your filters' : 'yet'}.
            </p>
          </div>
        ) : (
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--hairline)' }}>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: 'var(--canvas-soft)', borderBottom: '1px solid var(--hairline)' }}>
                    {['Time', 'User', 'Phone', 'Action', 'Form', 'Status', 'Details'].map(h => (
                      <th key={h} className="text-left px-3 py-2.5 font-medium" style={{ color: 'var(--muted)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <AnimatePresence initial={false}>
                    {filtered.map((e, i) => {
                      const st = getStatusStyle(e.status || '')
                      return (
                        <motion.tr
                          key={e.id || i}
                          initial={{ opacity: 0, y: -10 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          style={{ background: i % 2 === 0 ? 'var(--surface-card)' : 'var(--canvas-soft)', borderBottom: '1px solid var(--hairline-soft)' }}
                        >
                          <td className="px-3 py-2 whitespace-nowrap" style={{ color: 'var(--muted)' }}>{formatTimestamp(e.timestamp)}</td>
                          <td className="px-3 py-2 font-mono" style={{ color: 'var(--body)' }}>{(e.user_id || '—').slice(0, 12)}</td>
                          <td className="px-3 py-2 font-mono" style={{ color: 'var(--body)' }}>{e.phone || '—'}</td>
                          <td className="px-3 py-2" style={{ color: 'var(--body)' }}>{e.action || '—'}</td>
                          <td className="px-3 py-2" style={{ color: 'var(--body)' }}>{e.form_type || '—'}</td>
                          <td className="px-3 py-2">
                            <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium" style={{ background: st.bg, color: st.text }}>
                              {e.status || 'unknown'}
                            </span>
                          </td>
                          <td className="px-3 py-2 max-w-[200px] truncate" style={{ color: 'var(--muted)' }}>{e.details || '—'}</td>
                        </motion.tr>
                      )
                    })}
                  </AnimatePresence>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
