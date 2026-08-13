/**
 * Agency identity: colour, short label, and how a requirement is attributed.
 *
 * Grouping key is `evidence.source_entity` — the entity the allowlist assigned,
 * not anything a model produced. Requirements with no accepted evidence have no
 * agency by definition, so they fall back to the node that produced them and are
 * shown as unattributed rather than being quietly filed under a real agency.
 */

import type { RequirementItem } from '../types/caseState'

export interface AgencyStyle {
  label: string
  short: string
  /** Neon accent — used for the border glow, chip, and heading. */
  color: string
}

export const AGENCY_STYLE: Record<string, AgencyStyle> = {
  'Saudi Business Center': { label: 'Saudi Business Center', short: 'SBC', color: '#9D7CFF' },
  'Ministry of Commerce': { label: 'Ministry of Commerce', short: 'MC', color: '#BEA9FF' },
  Balady: { label: 'Balady', short: 'BLD', color: '#5BCD84' },
  'Ministry of Municipalities and Housing': { label: 'Municipalities & Housing', short: 'MOMAH', color: '#5BCD84' },
  ZATCA: { label: 'ZATCA', short: 'ZTC', color: '#D9A441' },
  SFDA: { label: 'SFDA', short: 'SFDA', color: '#4FD1C5' },
  GOSI: { label: 'GOSI', short: 'GOSI', color: '#63B3ED' },
  Qiwa: { label: 'Qiwa', short: 'QIWA', color: '#63B3ED' },
  HRSD: { label: 'HRSD', short: 'HRSD', color: '#63B3ED' },
  SAIP: { label: 'SAIP', short: 'SAIP', color: '#F687B3' },
  "Monsha'at": { label: "Monsha'at", short: 'MON', color: '#9D7CFF' },
  'OpenStreetMap Overpass': { label: 'OpenStreetMap', short: 'OSM', color: '#8A8A9A' },
}

export const UNATTRIBUTED: AgencyStyle = {
  label: 'No verified source',
  short: '—',
  color: '#8A8A9A',
}

/** Which node produced a requirement, when no evidence survived to name an agency. */
const NODE_AGENCY: Record<string, string> = {
  commercial_registration: 'Ministry of Commerce',
  vat_registration: 'ZATCA',
  food_safety: 'SFDA',
  employment_social_insurance: 'GOSI',
  intellectual_property: 'SAIP',
  municipal_requirements: 'Balady',
  tax_financial: 'ZATCA',
}

export function agencyOf(requirement: RequirementItem): string | null {
  const entity = requirement.evidence?.source_entity
  if (entity) return entity
  // No accepted evidence — attribute by producing node so the card still lands
  // in a sensible group, but the caller renders it as unverified.
  return NODE_AGENCY[requirement.produced_by ?? ''] ?? null
}

export function styleFor(agency: string | null): AgencyStyle {
  if (!agency) return UNATTRIBUTED
  return AGENCY_STYLE[agency] ?? { label: agency, short: agency.slice(0, 4).toUpperCase(), color: '#9D7CFF' }
}

export interface AgencyGroup {
  agency: string | null
  style: AgencyStyle
  requirements: RequirementItem[]
  citedCount: number
}

export function groupByAgency(requirements: RequirementItem[]): AgencyGroup[] {
  const map = new Map<string, RequirementItem[]>()
  for (const requirement of requirements) {
    const key = agencyOf(requirement) ?? '__none__'
    const bucket = map.get(key)
    if (bucket) bucket.push(requirement)
    else map.set(key, [requirement])
  }

  return [...map.entries()]
    .map(([key, reqs]) => {
      const agency = key === '__none__' ? null : key
      return {
        agency,
        style: styleFor(agency),
        requirements: reqs,
        citedCount: reqs.filter(r => r.evidence?.source_url).length,
      }
    })
    // Agencies with real citations first; unattributed always last.
    .sort((a, b) => {
      if (!a.agency) return 1
      if (!b.agency) return -1
      return b.citedCount - a.citedCount || a.style.label.localeCompare(b.style.label)
    })
}

/**
 * The reason a requirement is in the state it is in.
 *
 * Prefers `status_reason`, which the backend evidence-evaluation work will add.
 * Until then `note` carries the same information, so this renders correctly now
 * and upgrades automatically without a second frontend change.
 */
export function statusReason(requirement: RequirementItem): string | null {
  const withReason = requirement as RequirementItem & { status_reason?: string | null }
  return (withReason.status_reason || requirement.note || '').trim() || null
}

/** "Live" / "Cached" / "Corpus" badge text for a requirement's evidence. */
export function retrievalLabel(requirement: RequirementItem): { text: string; color: string } | null {
  const path = requirement.evidence?.retrieval_path
  if (!path) return null
  if (path === 'live') return { text: 'Live', color: '#5BCD84' }
  if (path === 'corpus_fallback') return { text: 'Corpus', color: '#D9A441' }
  return null
}
