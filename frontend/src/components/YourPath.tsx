import { CheckCircle2, Circle, HelpCircle } from 'lucide-react'

import type { RequirementItem } from '../types/caseState'
import { statusReason, styleFor, agencyOf } from '../lib/agencies'

interface YourPathProps {
  requirements: RequirementItem[]
}

/**
 * Two-column Completed / Missing view.
 *
 * `requirement.status` is the single source of truth, so this renders correctly
 * automatically once the backend evidence-evaluation work lands — no second
 * frontend change needed:
 *
 *   satisfied  -> Completed
 *   missing    -> Missing
 *   unverified -> Missing column, but visually distinct (amber, "Unverified")
 *
 * The third bucket is deliberate. "We could not verify this" is an honest system
 * state, not an outstanding task, and collapsing it into "missing" would tell
 * the user to go do something that may already be satisfied. It sits in the
 * right-hand column because it still needs attention — just a different kind.
 */
export default function YourPath({ requirements }: YourPathProps) {
  if (requirements.length === 0) return null

  const completed = requirements.filter(r => r.status === 'satisfied')
  const missing = requirements.filter(r => r.status === 'missing')
  const unverified = requirements.filter(r => r.status === 'unverified')
  const outstanding = [...missing, ...unverified]

  const pct = Math.round((completed.length / requirements.length) * 100)

  return (
    <section id="your-path" className="py-16 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="mb-8">
          <p className="section-label mb-3">Your path</p>
          <div className="flex items-end justify-between gap-4 flex-wrap">
            <div>
              <h2
                className="font-extrabold tracking-tight mb-1"
                style={{ fontSize: 'clamp(22px, 3.5vw, 32px)', color: '#F1F1F1' }}
              >
                Where you stand
              </h2>
              <p className="text-sm" style={{ color: '#B0B0B0' }}>
                {completed.length} of {requirements.length} requirements confirmed
                {unverified.length > 0 && ` · ${unverified.length} could not be verified`}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span
                className="text-2xl font-extrabold tabular-nums"
                style={{ color: '#5BCD84', textShadow: '0 0 20px rgba(91,205,132,0.45)' }}
              >
                {pct}%
              </span>
              <div className="w-28 h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.07)' }}>
                <div
                  className="h-full rounded-full transition-[width] duration-500"
                  style={{ width: `${pct}%`, background: 'linear-gradient(90deg,#5BCD84,#93DEAE)' }}
                />
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Column
            title="Completed"
            subtitle="Confirmed against a cited source"
            accent="#5BCD84"
            items={completed}
            emptyText="Nothing confirmed yet."
          />
          <Column
            title="Missing"
            subtitle="Still to do, or not verifiable"
            accent="#D9A441"
            items={outstanding}
            emptyText="Nothing outstanding."
          />
        </div>
      </div>
    </section>
  )
}

function Column({
  title,
  subtitle,
  accent,
  items,
  emptyText,
}: {
  title: string
  subtitle: string
  accent: string
  items: RequirementItem[]
  emptyText: string
}) {
  return (
    <div
      className="rounded-2xl overflow-hidden flex flex-col"
      style={{
        background: 'rgba(23,27,61,0.7)',
        border: `1px solid ${accent}33`,
        boxShadow: `0 0 22px ${accent}14`,
      }}
    >
      <div style={{ height: 2, background: `linear-gradient(90deg, ${accent}, transparent)` }} />
      <header className="px-5 py-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold" style={{ color: accent, textShadow: `0 0 14px ${accent}55` }}>
            {title}
          </h3>
          <p className="text-[11px]" style={{ color: '#7A7A8A' }}>{subtitle}</p>
        </div>
        <span
          className="text-sm font-extrabold tabular-nums px-2.5 py-1 rounded-lg"
          style={{ color: accent, background: `${accent}14`, border: `1px solid ${accent}33` }}
        >
          {items.length}
        </span>
      </header>

      <div style={{ height: 1, background: 'rgba(255,255,255,0.06)' }} />

      {items.length === 0 ? (
        <p className="px-5 py-8 text-center text-xs" style={{ color: '#616161' }}>{emptyText}</p>
      ) : (
        <ul className="flex flex-col">
          {items.map((requirement, i) => {
            const reason = statusReason(requirement)
            const agency = styleFor(agencyOf(requirement))
            const isUnverified = requirement.status === 'unverified'
            const Icon = requirement.status === 'satisfied' ? CheckCircle2 : isUnverified ? HelpCircle : Circle
            const tone = requirement.status === 'satisfied' ? '#5BCD84' : isUnverified ? '#D9A441' : '#9D7CFF'

            return (
              <li
                key={`${requirement.name}-${i}`}
                className="px-5 py-3.5 flex items-start gap-3"
                style={{ borderTop: i === 0 ? 'none' : '1px solid rgba(255,255,255,0.05)' }}
              >
                <Icon size={15} strokeWidth={2.2} style={{ color: tone, marginTop: 1, flexShrink: 0 }} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2 mb-0.5">
                    <span className="text-[13px] font-medium leading-snug" style={{ color: '#E6E6EE' }}>
                      {requirement.name}
                    </span>
                    {isUnverified && (
                      <span
                        className="shrink-0 text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
                        style={{ color: '#D9A441', background: 'rgba(217,164,65,0.12)', border: '1px solid rgba(217,164,65,0.35)' }}
                      >
                        Unverified
                      </span>
                    )}
                  </div>
                  {reason && (
                    <p className="text-[11px] leading-relaxed mb-1" style={{ color: '#8A8A9A' }}>
                      {reason}
                    </p>
                  )}
                  <span className="text-[10px] font-semibold" style={{ color: agency.color }}>
                    {agency.label}
                  </span>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
