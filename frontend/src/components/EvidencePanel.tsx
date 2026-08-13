import { useState } from 'react'
import { ExternalLink, ChevronDown, ChevronUp, ShieldCheck, Globe, FileText, MapPin, DollarSign, AlertTriangle } from 'lucide-react'
import type { EvidenceItem, EvidenceType } from '../types/bosalah'

// ─── Config ───────────────────────────────────────────────────────────────────

const TYPE_CONFIG: Record<EvidenceType, { label: string; icon: typeof Globe; color: string; bg: string; border: string }> = {
  regulation: { label: 'Regulation',  icon: ShieldCheck, color: '#BEA9FF', bg: 'rgba(129,116,201,0.1)', border: 'rgba(129,116,201,0.25)' },
  municipal:  { label: 'Municipal',   icon: MapPin,      color: '#93DEAE', bg: 'rgba(91,205,132,0.08)',  border: 'rgba(91,205,132,0.2)'   },
  financial:  { label: 'Financial',   icon: DollarSign,  color: '#D9A441', bg: 'rgba(217,164,65,0.08)', border: 'rgba(217,164,65,0.2)'   },
  document:   { label: 'Document',    icon: FileText,    color: '#9D7CFF', bg: 'rgba(157,124,255,0.08)', border: 'rgba(157,124,255,0.2)'  },
  web:        { label: 'Web Source',  icon: Globe,       color: '#B0B0B0', bg: 'rgba(255,255,255,0.04)', border: 'rgba(255,255,255,0.1)'  },
}

const FILTERS: Array<{ key: EvidenceType | 'all'; label: string }> = [
  { key: 'all',        label: 'All' },
  { key: 'regulation', label: 'Regulation' },
  { key: 'municipal',  label: 'Municipal' },
  { key: 'financial',  label: 'Financial' },
  { key: 'document',   label: 'Document' },
  { key: 'web',        label: 'Web' },
]

function ConfidenceDots({ value }: { value: number }) {
  const filled = Math.round(value * 5)
  return (
    <div className="flex items-center gap-0.5" title={`${Math.round(value * 100)}% confidence`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className="inline-block rounded-full"
          style={{
            width: 6, height: 6,
            background: i < filled ? '#5BCD84' : 'rgba(255,255,255,0.1)',
          }}
        />
      ))}
    </div>
  )
}

function EvidenceCard({ item }: { item: EvidenceItem }) {
  const [expanded, setExpanded] = useState(false)
  const cfg = TYPE_CONFIG[item.type]
  const Icon = cfg.icon

  return (
    <div
      className="rounded-xl overflow-hidden transition-all duration-200"
      style={{ background: '#10122B', border: `1px solid ${cfg.border}` }}
    >
      {/* Header row */}
      <button
        className="w-full text-left px-4 py-3 flex items-start gap-3"
        onClick={() => setExpanded(v => !v)}
      >
        {/* Type icon */}
        <div
          className="shrink-0 flex items-center justify-center rounded-lg mt-0.5"
          style={{ width: 30, height: 30, background: cfg.bg, border: `1px solid ${cfg.border}` }}
        >
          <Icon size={13} style={{ color: cfg.color }} />
        </div>

        <div className="flex-1 min-w-0">
          {/* Claim */}
          <p className="text-sm font-medium leading-snug mb-1" style={{ color: '#F1F1F1' }}>
            {item.claim}
          </p>
          {/* Source + agent */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium" style={{ color: cfg.color }}>{item.source}</span>
            <span style={{ color: '#3A3D60' }}>·</span>
            <span className="text-xs" style={{ color: '#616161' }}>{item.agentName}</span>
            <span style={{ color: '#3A3D60' }}>·</span>
            <ConfidenceDots value={item.confidence} />
          </div>
        </div>

        <div className="shrink-0 flex items-center gap-2 ml-2">
          {expanded
            ? <ChevronUp size={13} style={{ color: '#616161' }} />
            : <ChevronDown size={13} style={{ color: '#616161' }} />
          }
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div
          className="px-4 pb-4 pt-0 border-t"
          style={{ borderColor: cfg.border }}
        >
          {item.excerpt && (
            <blockquote
              className="text-xs leading-relaxed italic my-3 pl-3"
              style={{
                color: '#B0B0B0',
                borderLeft: `2px solid ${cfg.color}`,
              }}
            >
              "{item.excerpt}"
            </blockquote>
          )}
          <div className="flex items-center justify-between gap-4 flex-wrap mt-2">
            <span className="text-xs" style={{ color: '#616161' }}>
              {new Date(item.timestamp).toLocaleString('en-SA', { dateStyle: 'medium', timeStyle: 'short' })}
            </span>
            <a
              href={item.reference}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-medium transition-colors"
              style={{ color: cfg.color }}
              onClick={e => e.stopPropagation()}
            >
              View source <ExternalLink size={10} />
            </a>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Panel ────────────────────────────────────────────────────────────────────

interface EvidencePanelProps {
  evidence: EvidenceItem[]
}

export default function EvidencePanel({ evidence }: EvidencePanelProps) {
  const [activeFilter, setActiveFilter] = useState<EvidenceType | 'all'>('all')
  const [search, setSearch] = useState('')

  const filtered = evidence.filter(e => {
    const matchType = activeFilter === 'all' || e.type === activeFilter
    const q = search.toLowerCase()
    const matchSearch = q === '' || e.claim.toLowerCase().includes(q) || e.source.toLowerCase().includes(q)
    return matchType && matchSearch
  })

  return (
    <section id="evidence" className="py-16 px-6">
      <div className="max-w-5xl mx-auto">

        {/* Header */}
        <div className="mb-8 animate-fade-up">
          <p className="section-label mb-3">Evidence &amp; Sources</p>
          <h2
            className="font-extrabold tracking-tight mb-2"
            style={{ fontSize: 'clamp(22px, 3.5vw, 32px)', color: '#F1F1F1' }}
          >
            Every claim, cited.
          </h2>
          <p className="text-sm" style={{ color: '#B0B0B0' }}>
            Bosalah shows you the source behind every regulation, fee, and requirement — nothing is taken on faith.
          </p>
        </div>

        {/* Search + filter bar */}
        <div className="flex flex-col sm:flex-row gap-3 mb-5">
          <input
            type="text"
            placeholder="Search claims or sources…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="field-input flex-1"
            style={{ maxWidth: 300 }}
          />
          <div className="flex flex-wrap gap-2">
            {FILTERS.map(f => {
              const active = activeFilter === f.key
              return (
                <button
                  key={f.key}
                  onClick={() => setActiveFilter(f.key)}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150"
                  style={{
                    background: active ? 'rgba(157,124,255,0.18)' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${active ? 'rgba(157,124,255,0.5)' : 'rgba(255,255,255,0.08)'}`,
                    color: active ? '#9D7CFF' : '#616161',
                  }}
                >
                  {f.label}
                  {f.key !== 'all' && (
                    <span className="ml-1.5 opacity-60">
                      {evidence.filter(e => e.type === f.key).length}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>

        {/* Stats row */}
        <div className="flex gap-6 mb-6 flex-wrap">
          {[
            { label: 'Total sources', value: evidence.length, color: '#9D7CFF' },
            { label: 'High confidence (≥80%)', value: evidence.filter(e => e.confidence >= 0.8).length, color: '#5BCD84' },
            { label: 'With excerpts', value: evidence.filter(e => e.excerpt).length, color: '#BEA9FF' },
          ].map(s => (
            <div key={s.label} className="flex items-center gap-2">
              <span className="text-xl font-bold tabular-nums" style={{ color: s.color }}>{s.value}</span>
              <span className="text-xs" style={{ color: '#616161' }}>{s.label}</span>
            </div>
          ))}
        </div>

        {/* Evidence list */}
        {filtered.length === 0 ? (
          <div
            className="flex flex-col items-center gap-3 py-16 rounded-2xl"
            style={{ background: 'rgba(23,27,61,0.4)', border: '1px dashed rgba(129,116,201,0.15)' }}
          >
            <AlertTriangle size={24} style={{ color: '#616161' }} />
            <p className="text-sm" style={{ color: '#616161' }}>No evidence matches your filter.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {filtered.map(item => <EvidenceCard key={item.id} item={item} />)}
          </div>
        )}
      </div>
    </section>
  )
}
