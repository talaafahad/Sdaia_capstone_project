import { useState } from 'react'
import { Info, AlertTriangle, CheckCircle2, XCircle, ChevronDown, ChevronUp, Code } from 'lucide-react'
import type { AuditEntry, AuditSeverity } from '../types/bosalah'

// ─── Config ───────────────────────────────────────────────────────────────────

const SEV_CONFIG: Record<AuditSeverity, {
  icon: typeof Info
  color: string
  bg: string
  border: string
  label: string
}> = {
  info:    { icon: Info,          color: '#BEA9FF', bg: 'rgba(190,169,255,0.07)', border: 'rgba(129,116,201,0.2)', label: 'Info'    },
  success: { icon: CheckCircle2,  color: '#5BCD84', bg: 'rgba(91,205,132,0.07)', border: 'rgba(91,205,132,0.2)',  label: 'Success' },
  warning: { icon: AlertTriangle, color: '#D9A441', bg: 'rgba(217,164,65,0.07)', border: 'rgba(217,164,65,0.2)',  label: 'Warning' },
  error:   { icon: XCircle,       color: '#C0564B', bg: 'rgba(192,86,75,0.07)',  border: 'rgba(192,86,75,0.2)',   label: 'Error'   },
}

// ─── Single entry ─────────────────────────────────────────────────────────────

function AuditRow({ entry }: { entry: AuditEntry }) {
  const [showDetail, setShowDetail] = useState(false)
  const cfg = SEV_CONFIG[entry.severity]
  const Icon = cfg.icon

  // Format ISO → HH:MM:SS
  const time = new Date(entry.timestamp).toLocaleTimeString('en-SA', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

  return (
    <div
      className="rounded-lg overflow-hidden transition-all"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      <div className="flex items-start gap-3 px-3 py-2.5">
        {/* Severity icon */}
        <div className="shrink-0 mt-0.5">
          <Icon size={13} style={{ color: cfg.color }} strokeWidth={2} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-xs leading-snug" style={{ color: '#D4D4D4' }}>
            {entry.message}
          </p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="text-[10px] font-mono tabular-nums" style={{ color: '#616161' }}>
              {time}
            </span>
            <span style={{ color: '#3A3D60' }}>·</span>
            <span
              className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded"
              style={{ background: `${cfg.color}18`, color: cfg.color }}
            >
              {cfg.label}
            </span>
          </div>
        </div>

        {/* Detail toggle */}
        {entry.detail && (
          <button
            className="shrink-0 ml-1"
            onClick={() => setShowDetail(v => !v)}
            title="Show raw detail"
          >
            {showDetail
              ? <ChevronUp  size={12} style={{ color: '#616161' }} />
              : <Code size={12} style={{ color: '#616161' }} />
            }
          </button>
        )}
      </div>

      {/* Raw detail */}
      {showDetail && entry.detail && (
        <pre
          className="text-[11px] leading-relaxed px-3 pb-3 pt-0 overflow-x-auto"
          style={{ color: '#93DEAE', fontFamily: 'monospace', borderTop: `1px solid ${cfg.border}` }}
        >
          {entry.detail}
        </pre>
      )}
    </div>
  )
}

// ─── Audit log panel (used inside AgentRoster cards + as standalone) ──────────

interface AuditLogProps {
  /** Agent name shown in the header */
  agentName: string
  entries: AuditEntry[]
  /** If true, panel starts collapsed */
  defaultCollapsed?: boolean
}

export default function AuditLog({ agentName, entries, defaultCollapsed = false }: AuditLogProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  const warnings = entries.filter(e => e.severity === 'warning' || e.severity === 'error').length

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: 'rgba(16,18,43,0.7)', border: '1px solid rgba(129,116,201,0.15)' }}
    >
      {/* Header */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        onClick={() => setCollapsed(v => !v)}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold" style={{ color: '#F1F1F1' }}>
            Audit Log — {agentName}
          </span>
          <span
            className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full"
            style={{ background: 'rgba(129,116,201,0.12)', color: '#9D7CFF', border: '1px solid rgba(129,116,201,0.2)' }}
          >
            {entries.length} entries
          </span>
          {warnings > 0 && (
            <span
              className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full flex items-center gap-1"
              style={{ background: 'rgba(217,164,65,0.1)', color: '#D9A441', border: '1px solid rgba(217,164,65,0.2)' }}
            >
              <AlertTriangle size={9} />
              {warnings} warning{warnings > 1 ? 's' : ''}
            </span>
          )}
        </div>
        {collapsed
          ? <ChevronDown size={13} style={{ color: '#616161' }} />
          : <ChevronUp   size={13} style={{ color: '#616161' }} />
        }
      </button>

      {/* Entries */}
      {!collapsed && (
        <div
          className="px-3 pb-3 flex flex-col gap-1.5 max-h-72 overflow-y-auto"
          style={{ borderTop: '1px solid rgba(129,116,201,0.1)' }}
        >
          <div className="pt-3" />
          {entries.length === 0 ? (
            <p className="text-xs text-center py-4" style={{ color: '#616161' }}>No log entries yet.</p>
          ) : (
            entries.map(entry => <AuditRow key={entry.id} entry={entry} />)
          )}
        </div>
      )}
    </div>
  )
}
