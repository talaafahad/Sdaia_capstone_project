import { CheckCircle2, HelpCircle, Circle, ExternalLink, Globe } from 'lucide-react'

import type { RequirementItem, SupplementaryItem } from '../types/caseState'
import { groupByAgency, retrievalLabel, statusReason } from '../lib/agencies'

interface RegulationsFoundProps {
  requirements: RequirementItem[]
  /** Open-web references. Rendered in a deliberately muted card — never neon,
   *  never with satisfied/verified language, never counted as an agency. */
  supplementary?: SupplementaryItem[]
}

/** Grey, non-neon. Sits among the agency cards but must never be mistakable
 *  for one at a glance — hence the neutral palette and the explicit header. */
function NonGovernmentCard({ items }: { items: SupplementaryItem[] }) {
  const MUTED = '#8A8A9A'
  return (
    <article
      className="rounded-2xl overflow-hidden flex flex-col"
      style={{
        background: 'rgba(255,255,255,0.02)',
        border: '1px dashed rgba(255,255,255,0.14)',
        // No glow. The agency cards get a neon boxShadow; this deliberately does not.
      }}
    >
      <header className="px-5 pt-4 pb-3 flex items-center gap-2.5">
        <span
          className="shrink-0 inline-flex items-center justify-center rounded-lg"
          style={{ width: 34, height: 34, color: MUTED, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)' }}
        >
          <Globe size={15} />
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-bold" style={{ color: '#C9C9D4' }}>
            Non-government sources
          </h3>
          <p className="text-[11px] leading-snug" style={{ color: '#7A7A8A' }}>
            Not verified against an official government source — for reference only.
          </p>
        </div>
      </header>

      <div style={{ height: 1, background: 'rgba(255,255,255,0.08)' }} />

      <ul className="flex-1 flex flex-col">
        {items.map((item, i) => (
          <li
            key={`${item.source_url}-${i}`}
            className="px-5 py-3"
            style={{ borderTop: i === 0 ? 'none' : '1px solid rgba(255,255,255,0.05)' }}
          >
            <div className="flex items-start justify-between gap-2.5 mb-1">
              <span className="text-[13px] leading-snug" style={{ color: '#C9C9D4' }}>
                {item.claim}
              </span>
              <span
                className="shrink-0 text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
                style={{ color: MUTED, background: 'rgba(255,255,255,0.04)', border: `1px solid ${MUTED}44` }}
              >
                Low
              </span>
            </div>
            <a
              href={item.source_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-[10px] hover:underline break-all"
              style={{ color: MUTED }}
            >
              <ExternalLink size={9} />
              {item.source_domain || item.source_url}
            </a>
          </li>
        ))}
      </ul>
    </article>
  )
}

/** Status chip. "Unverified" is deliberately amber and NOT red — it is an
 *  honest system state ("we could not confirm this"), not a failure. */
function StatusChip({ status }: { status: RequirementItem['status'] }) {
  const cfg =
    status === 'satisfied'
      ? { label: 'Verified', color: '#5BCD84', Icon: CheckCircle2 }
      : status === 'missing'
        ? { label: 'Required', color: '#9D7CFF', Icon: Circle }
        : { label: 'Unverified', color: '#D9A441', Icon: HelpCircle }

  return (
    <span
      className="shrink-0 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
      style={{ color: cfg.color, background: `${cfg.color}14`, border: `1px solid ${cfg.color}40` }}
    >
      <cfg.Icon size={9} strokeWidth={2.5} />
      {cfg.label}
    </span>
  )
}

export default function RegulationsFound({ requirements, supplementary = [] }: RegulationsFoundProps) {
  if (requirements.length === 0 && supplementary.length === 0) return null

  const groups = groupByAgency(requirements)
  const cited = requirements.filter(r => r.evidence?.source_url).length

  return (
    <section id="regulations" className="py-16 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="mb-8">
          <p className="section-label mb-3">Regulations found</p>
          <h2
            className="font-extrabold tracking-tight mb-2"
            style={{ fontSize: 'clamp(22px, 3.5vw, 32px)', color: '#F1F1F1' }}
          >
            {requirements.length} requirements across {groups.filter(g => g.agency).length} agencies
          </h2>
          <p className="text-sm" style={{ color: '#B0B0B0' }}>
            Grouped by the agency that owns each rule. {cited} of {requirements.length} carry a
            citation that survived the Verifier.
          </p>
        </div>

        {/* items-start so a card sizes to its own content — without it every
            card stretches to the tallest in the row, leaving dead space under
            the agencies that found fewer requirements. */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5 items-start">
          {groups.map(group => (
            <article
              key={group.agency ?? '__none__'}
              className="rounded-2xl overflow-hidden flex flex-col transition-transform duration-200 hover:-translate-y-0.5"
              style={{
                background: 'rgba(23,27,61,0.72)',
                border: `1px solid ${group.style.color}40`,
                // The neon: an outer glow plus an inner top highlight.
                boxShadow: `0 0 24px ${group.style.color}1F, inset 0 1px 0 ${group.style.color}26`,
              }}
            >
              {/* Neon top rule */}
              <div
                style={{
                  height: 2,
                  background: `linear-gradient(90deg, transparent, ${group.style.color}, transparent)`,
                }}
              />

              <header className="px-5 pt-4 pb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5 min-w-0">
                  <span
                    className="shrink-0 inline-flex items-center justify-center text-[10px] font-extrabold rounded-lg"
                    style={{
                      width: 34,
                      height: 34,
                      color: group.style.color,
                      background: `${group.style.color}14`,
                      border: `1px solid ${group.style.color}3A`,
                      textShadow: `0 0 10px ${group.style.color}66`,
                    }}
                  >
                    {group.style.short}
                  </span>
                  <div className="min-w-0">
                    <h3
                      className="text-sm font-bold truncate"
                      style={{ color: '#F1F1F1', textShadow: `0 0 16px ${group.style.color}40` }}
                    >
                      {group.style.label}
                    </h3>
                    <p className="text-[11px]" style={{ color: '#7A7A8A' }}>
                      {group.requirements.length} requirement
                      {group.requirements.length === 1 ? '' : 's'}
                      {group.agency ? ` · ${group.citedCount} cited` : ' · no citation'}
                    </p>
                  </div>
                </div>
              </header>

              <div style={{ height: 1, background: `${group.style.color}1F` }} />

              <ul className="flex-1 flex flex-col">
                {group.requirements.map((requirement, i) => {
                  const reason = statusReason(requirement)
                  const retrieval = retrievalLabel(requirement)
                  return (
                    <li
                      key={`${requirement.name}-${i}`}
                      className="px-5 py-3"
                      style={{
                        borderTop: i === 0 ? 'none' : '1px solid rgba(255,255,255,0.05)',
                      }}
                    >
                      <div className="flex items-start justify-between gap-2.5 mb-1">
                        <span
                          className="text-[13px] font-medium leading-snug"
                          style={{ color: '#E6E6EE' }}
                        >
                          {requirement.name}
                        </span>
                        <StatusChip status={requirement.status} />
                      </div>

                      {reason && (
                        <p
                          className="text-[11px] leading-relaxed mb-1.5"
                          style={{ color: '#8A8A9A' }}
                        >
                          {reason}
                        </p>
                      )}

                      <div className="flex items-center gap-2 flex-wrap">
                        {retrieval && (
                          <span
                            className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded"
                            style={{
                              color: retrieval.color,
                              background: `${retrieval.color}12`,
                              border: `1px solid ${retrieval.color}33`,
                            }}
                            title="Which retrieval path served this claim"
                          >
                            {retrieval.text}
                          </span>
                        )}
                        {requirement.evidence?.source_url && (
                          <a
                            href={requirement.evidence.source_url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="inline-flex items-center gap-1 text-[10px] hover:underline"
                            style={{ color: group.style.color }}
                          >
                            <ExternalLink size={9} />
                            source
                          </a>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ul>
            </article>
          ))}

          {/* Open-web references. Inside the same section so the contrast with
              the agency cards is immediate, but never styled as one. */}
          {supplementary.length > 0 && <NonGovernmentCard items={supplementary} />}
        </div>
      </div>
    </section>
  )
}
