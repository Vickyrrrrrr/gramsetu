'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowLeft, RefreshCw, Shield, Clock, CheckCircle2, AlertTriangle,
  Loader2, Search, Filter, LogOut,
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════
   TYPES
   ═══════════════════════════════════════════════════════════════ */

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

/* ═══════════════════════════════════════════════════════════════
   CONSTANTS
   ═══════════════════════════════════════════════════════════════ */

const ADMIN_TOKEN = 'gramsetu-admin-2025'
const POLL_INTERVAL = 5000

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  completed:   { bg: '#dcfce7', text: '#166534' },
  success:     { bg: '#dcfce7', text: '#166534' },
  in_progress: { bg: '#fef3c7', text: '#92400e' },
  pending:     { bg: '#fef3c7', text: '#92400e' },
  processing:  { bg: '#dbeafe', text: '#1e40af' },
  failed:      { bg: '#fee2e2', text: '#991b1b' },
  error:       { bg: '#fee2e2', text: '#991b1b' },
}

function getStatusStyle(status: string) {
  const normalized = status.toLowerCase().replace(/[\s-]/g, '_')
  return STATUS_COLORS[normalized] || { bg: '#f3f4f6', text: '#374151' }
}

function formatTimestamp(ts: string) {
  try {
    const d = new Date(ts)
    return d.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ts
  }
}

/* ═══════════════════════════════════════════════════════════════
   PASSWORD GATE
   ═══════════════════════════════════════════════════════════════ */

function PasswordGate({ onUnlock }: { onUnlock: () => void }) {
  const [pw, setPw] = useState('')
  const [error, setError] = useState(false)

  const envPw = typeof window !== 'undefined'
    ? (window as unknown as Record<string, string>)?.NEXT_PUBLIC_ADMIN_PASSWORD
    : undefined

  const correctPw = envPw || 'gramsetu2025'

  const submit = () => {
    if (pw === correctPw) {
      if (typeof window !== 'undefined') {
        sessionStorage.setItem('gramsetu_admin_auth', '1')
      }
      onUnlock()
    } else {
      setError(true)
      setTimeout(() => setError(false), 2000)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: '#F7F6F3' }}
    >
      <div
        className="w-full max-w-sm rounded-2xl p-6"
        style={{ background: 'white', border: '1px solid #E5E5E0' }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Shield size={20} style={{ color: '#0C0C0C' }} />
          <h2 className="font-semibold text-base">Admin Dashboard</h2>
        </div>
        <p className="text-sm mb-4" style={{ color: '#6B6B6B' }}>
          Enter the admin password to access the audit dashboard.
        </p>
        <input
          autoFocus
          type="password"
          placeholder="Password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
          className="w-full px-3 py-2.5 rounded-lg text-sm outline-none mb-3"
          style={{
            border: `1px solid ${error ? '#ef4444' : '#E5E5E0'}`,
          }}
        />
        {error && (
          <p className="text-xs text-red-600 mb-2">Incorrect password</p>
        )}
        <button
          onClick={submit}
          className="w-full py-2.5 rounded-lg text-sm font-medium transition-opacity"
          style={{ background: '#0C0C0C', color: '#F7F6F3' }}
        >
          Unlock
        </button>
        <Link
          href="/"
          className="block text-center text-xs mt-3"
          style={{ color: '#6B6B6B' }}
        >
          ← Back to home
        </Link>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   STATS ROW
   ═══════════════════════════════════════════════════════════════ */

function StatsRow({ entries }: { entries: AuditEntry[] }) {
  const total = entries.length
  const completed = entries.filter(
    (e) => ['completed', 'success'].includes(e.status?.toLowerCase())
  ).length
  const inProgress = entries.filter(
    (e) => ['in_progress', 'pending', 'processing'].includes(e.status?.toLowerCase().replace(/[\s-]/g, '_'))
  ).length
  const latencies = entries.filter((e) => e.latency_ms).map((e) => e.latency_ms!)
  const avgLatency = latencies.length > 0
    ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length)
    : 0

  const cards = [
    { label: 'Total Applications', value: total, icon: <Filter size={14} /> },
    { label: 'Completed', value: completed, icon: <CheckCircle2 size={14} className="text-green-600" /> },
    { label: 'In Progress', value: inProgress, icon: <Clock size={14} className="text-amber-600" /> },
    { label: 'Avg Latency', value: avgLatency ? `${avgLatency}ms` : '—', icon: <AlertTriangle size={14} className="text-blue-600" /> },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      {cards.map((c) => (
        <div
          key={c.label}
          className="p-4 rounded-lg"
          style={{ background: 'white', border: '1px solid #E5E5E0' }}
        >
          <div className="flex items-center gap-2 mb-1">
            {c.icon}
            <span className="text-xs" style={{ color: '#6B6B6B' }}>{c.label}</span>
          </div>
          <p className="text-xl font-semibold">{c.value}</p>
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   MAIN ADMIN PAGE
   ═══════════════════════════════════════════════════════════════ */

export default function AdminPage() {
  const [authed, setAuthed] = useState(false)
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [filterType, setFilterType] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [paused, setPaused] = useState(false)

  // Check if already authed
  useEffect(() => {
    if (typeof window !== 'undefined' && sessionStorage.getItem('gramsetu_admin_auth') === '1') {
      setAuthed(true)
    }
  }, [])

  // Fetch audit logs
  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(`/api/audit-logs?token=${ADMIN_TOKEN}`)
      if (!res.ok) return
      const data = await res.json()
      if (Array.isArray(data.logs)) {
        setEntries(data.logs)
      } else if (Array.isArray(data)) {
        setEntries(data)
      }
    } catch {
      // backend down
    } finally {
      setLoading(false)
    }
  }, [])

  // Poll every 5s
  useEffect(() => {
    if (!authed) return
    fetchLogs()
    if (paused) return
    const interval = setInterval(fetchLogs, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [authed, fetchLogs, paused])

  // Filter
  const formTypes = Array.from(new Set(entries.map((e) => e.form_type).filter(Boolean)))
  const filtered = entries.filter((e) => {
    if (filterType !== 'all' && e.form_type !== filterType) return false
    if (searchTerm) {
      const q = searchTerm.toLowerCase()
      return (
        (e.user_id || '').toLowerCase().includes(q) ||
        (e.phone || '').toLowerCase().includes(q) ||
        (e.action || '').toLowerCase().includes(q) ||
        (e.details || '').toLowerCase().includes(q)
      )
    }
    return true
  })

  if (!authed) return <PasswordGate onUnlock={() => setAuthed(true)} />

  return (
    <div className="min-h-screen" style={{ background: '#F7F6F3' }}>
      {/* ── Header ───────────────────────────────────────────── */}
      <header
        className="sticky top-0 z-10 flex items-center justify-between px-6 py-3"
        style={{ background: 'white', borderBottom: '1px solid #E5E5E0' }}
      >
        <div className="flex items-center gap-3">
          <Link href="/" style={{ color: '#6B6B6B' }}>
            <ArrowLeft size={18} />
          </Link>
          <div>
            <p className="font-semibold text-sm leading-tight flex items-center gap-1.5">
              <Shield size={14} /> Admin Dashboard
            </p>
            <p className="text-xs" style={{ color: '#6B6B6B' }}>
              Live audit feed · {entries.length} records
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setPaused(!paused)}
            className="text-xs px-3 py-1 rounded-full flex items-center gap-1"
            style={{
              border: '1px solid #E5E5E0',
              color: paused ? '#dc2626' : '#6B6B6B',
            }}
          >
            {paused ? '▶ Resume' : '⏸ Pause'}
          </button>
          <button
            onClick={fetchLogs}
            className="text-xs px-3 py-1 rounded-full flex items-center gap-1"
            style={{ border: '1px solid #E5E5E0', color: '#6B6B6B' }}
          >
            <RefreshCw size={11} /> Refresh
          </button>
          <button
            onClick={() => {
              sessionStorage.removeItem('gramsetu_admin_auth')
              setAuthed(false)
            }}
            className="text-xs px-3 py-1 rounded-full flex items-center gap-1"
            style={{ border: '1px solid #E5E5E0', color: '#6B6B6B' }}
          >
            <LogOut size={11} /> Logout
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-6">
        {/* ── Stats row ──────────────────────────────────────── */}
        <StatsRow entries={entries} />

        {/* ── Filters ────────────────────────────────────────── */}
        <div className="flex flex-wrap gap-3 mb-4">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search size={14} className="absolute left-3 top-2.5" style={{ color: '#6B6B6B' }} />
            <input
              type="text"
              placeholder="Search by user, phone, action…"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg text-xs outline-none"
              style={{ border: '1px solid #E5E5E0' }}
            />
          </div>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="text-xs px-3 py-2 rounded-lg outline-none"
            style={{ border: '1px solid #E5E5E0' }}
          >
            <option value="all">All form types</option>
            {formTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        {/* ── Table ──────────────────────────────────────────── */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={24} className="animate-spin" style={{ color: '#6B6B6B' }} />
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-sm" style={{ color: '#6B6B6B' }}>
              No audit entries {searchTerm || filterType !== 'all' ? 'match your filters' : 'yet'}.
            </p>
            <p className="text-xs mt-1" style={{ color: '#9CA3AF' }}>
              Start processing applications to see logs here.
            </p>
          </div>
        ) : (
          <div
            className="rounded-lg overflow-hidden"
            style={{ border: '1px solid #E5E5E0' }}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: '#f9fafb', borderBottom: '1px solid #E5E5E0' }}>
                    <th className="text-left px-3 py-2.5 font-medium" style={{ color: '#6B6B6B' }}>Time</th>
                    <th className="text-left px-3 py-2.5 font-medium" style={{ color: '#6B6B6B' }}>User</th>
                    <th className="text-left px-3 py-2.5 font-medium" style={{ color: '#6B6B6B' }}>Phone</th>
                    <th className="text-left px-3 py-2.5 font-medium" style={{ color: '#6B6B6B' }}>Action</th>
                    <th className="text-left px-3 py-2.5 font-medium" style={{ color: '#6B6B6B' }}>Form</th>
                    <th className="text-left px-3 py-2.5 font-medium" style={{ color: '#6B6B6B' }}>Status</th>
                    <th className="text-left px-3 py-2.5 font-medium" style={{ color: '#6B6B6B' }}>Details</th>
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
                          style={{
                            background: i % 2 === 0 ? 'white' : '#fafafa',
                            borderBottom: '1px solid #f3f4f6',
                          }}
                        >
                          <td className="px-3 py-2 whitespace-nowrap" style={{ color: '#6B6B6B' }}>
                            {formatTimestamp(e.timestamp)}
                          </td>
                          <td className="px-3 py-2 font-mono" style={{ color: '#374151' }}>
                            {(e.user_id || '—').slice(0, 12)}
                          </td>
                          <td className="px-3 py-2 font-mono" style={{ color: '#374151' }}>
                            {e.phone || '—'}
                          </td>
                          <td className="px-3 py-2" style={{ color: '#374151' }}>
                            {e.action || '—'}
                          </td>
                          <td className="px-3 py-2" style={{ color: '#374151' }}>
                            {e.form_type || '—'}
                          </td>
                          <td className="px-3 py-2">
                            <span
                              className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                              style={{ background: st.bg, color: st.text }}
                            >
                              {e.status || 'unknown'}
                            </span>
                          </td>
                          <td className="px-3 py-2 max-w-[200px] truncate" style={{ color: '#6B6B6B' }}>
                            {e.details || '—'}
                          </td>
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
